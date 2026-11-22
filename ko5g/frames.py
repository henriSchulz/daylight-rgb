"""Rendering text/images into frame packets for the Ko5G colour controller."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from .protocol import Config

DEFAULT_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def parse_color(c) -> tuple:
    if isinstance(c, (tuple, list)):
        return tuple(int(x) for x in c[:3])
    c = str(c).lstrip("#")
    named = {"red": "ff0000", "green": "00ff00", "blue": "0000ff", "white": "ffffff", "yellow": "ffff00",
             "orange": "ff8000", "cyan": "00ffff", "magenta": "ff00ff", "black": "000000"}
    c = named.get(c.lower(), c)
    return tuple(bytes.fromhex(c))


# -- pixel layout ---------------------------------------------------------------
def compose(img: Image.Image, cfg: Config) -> bytes:
    """Reorder a width x height RGB image fragment by fragment (ImageGenerator.ComposeDataComplex)."""
    img = img.convert("RGB")
    if img.size != (cfg.width, cfg.height):
        raise ValueError(f"image must be {cfg.width}x{cfg.height}, got {img.size}")
    fw, fh = cfg.fragment_size
    cols = cfg.fragment_columns
    raw = img.tobytes()
    out = bytearray()
    for idx in cfg.fragment_order():
        fx, fy = (idx % cols) * fw, (idx // cols) * fh
        for y in range(fh):
            o = ((fy + y) * cfg.width + fx) * 3
            out += raw[o:o + fw * 3]
    return bytes(out)


# -- run-length compression (Command.AddFrame, compressed flag = 1) ---------------------------
# Tokens over RGB pixels:
#   n, r, g, b            -> pixel (r,g,b) repeated n+1 times   (n = 0..253)
#   0xFF, n, n+1 pixels   -> n+1 literal pixels                  (n = 0..254)
MAX_REPEAT = 253
MAX_LITERAL = 254


def rle_encode(data: bytes) -> bytes:
    px = [data[i:i + 3] for i in range(0, len(data), 3)]
    out = bytearray()
    i, n = 0, len(px)
    while i < n:
        j = i
        while j + 1 < n and px[j + 1] == px[i] and j - i < MAX_REPEAT:
            j += 1
        if j > i:                        # run of >= 2 equal pixels
            out += bytes([j - i]) + px[i]
            i = j + 1
            continue
        k = i                            # literals until the next pair of equal pixels
        while k + 1 < n and px[k + 1] != px[k] and k - i < MAX_LITERAL:
            k += 1
        if k > i and k + 1 < n and px[k + 1] == px[k]:
            k -= 1                       # leave px[k] to start the next run
        if k == i:
            out += bytes([0]) + px[i]    # single pixel as a run of 1
        else:
            out += bytes([0xFF, k - i]) + b"".join(px[i:k + 1])
        i = k + 1
    return bytes(out)


def rle_decode(enc: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(enc):
        if enc[i] == 0xFF:
            n = enc[i + 1] + 1
            out += enc[i + 2:i + 2 + 3 * n]
            i += 2 + 3 * n
        else:
            out += enc[i + 1:i + 4] * (enc[i] + 1)
            i += 4
    return bytes(out)


def special_buffer_size(cfg: Config) -> int:
    """Special frames use the vendor app's buffer size: both board dimensions taken as board *width*
    (Command.AddFrame), e.g. 288 x 32 x 3 = 27648 for 32x16 boards. Verified on the device."""
    from .protocol import _PIXEL_H, _PIXEL_W
    pw, ph = _PIXEL_W[cfg.board_type], _PIXEL_H[cfg.board_type]
    return cfg.width * (cfg.height // ph) * pw * 3


def frame_packet(index: int, data: bytes, duration: int, special: bytes | None = None,
                 special_size: int = 0, compress: bool = False) -> bytes:
    """8-byte header (frame no., compressed flag, special flag, data length, duration) + data.
    Special frames: data padded to `special_size`, then the 66-byte trailer.
    compress: RLE if it is smaller than 90 % of the raw data (as the vendor app does)."""
    flag = 0
    if compress and not special:
        enc = rle_encode(data)
        if len(enc) < 0.9 * len(data):
            data, flag = enc, 1
    hdr = bytes([index >> 8 & 255, index & 255, flag, 1 if special else 0,
                 len(data) >> 8 & 255, len(data) & 255, duration >> 8 & 255, duration & 255])
    if special:
        return hdr + data.ljust(special_size, b"\0") + special
    return hdr + data


# -- special frames (clock / date / temperature drawn by the controller) -----------------
@dataclass
class Special:
    """Parameters of a 'special' frame (CompositionFrame$SpecialColor, 66-byte trailer)."""
    time: bool = False
    date: bool = False
    temp: bool = False
    clock: bool = False            # analogue clock
    time_pos: tuple = (0, 0)
    date_pos: tuple = (0, 0)
    temp_pos: tuple = (0, 0)
    clock_pos: tuple = (0, 0)
    time_format: int = 0
    date_format: int = 0
    temp_format: int = 0
    time_color: tuple = (255, 255, 255)
    date_color: tuple = (255, 255, 255)
    temp_color: tuple = (255, 255, 255)
    clock_second: tuple = (255, 255, 255)
    clock_minute: tuple = (12, 121, 219)
    clock_hour: tuple = (154, 156, 155)
    clock_frame: tuple = (0, 101, 189)
    clock_table: tuple = (13, 52, 83)
    clock_opacity: int = 255
    clock_all_visible: bool = True
    time_font: int = 0             # app value; sent as value-1 when > 0
    date_font: int = 0
    temp_font: int = 0
    clock_size: int = 0
    show_order: int = 228          # app default (-28 as signed byte)

    def trailer(self) -> bytes:
        t = bytearray(66)
        t[0], t[1], t[2], t[3] = int(self.time), int(self.date), int(self.temp), int(self.clock)
        for i, (x, y) in enumerate([self.time_pos, self.date_pos, self.temp_pos, self.clock_pos]):
            t[4 + 4 * i:6 + 4 * i] = int(x).to_bytes(2, "little")
            t[6 + 4 * i:8 + 4 * i] = int(y).to_bytes(2, "little")
        t[20], t[21], t[22] = self.time_format, self.date_format, self.temp_format
        cols = [self.time_color, self.date_color, self.temp_color, self.clock_second, self.clock_minute,
                self.clock_hour, self.clock_frame, self.clock_table]
        for i, c in enumerate(cols):
            t[23 + 3 * i:26 + 3 * i] = bytes(parse_color(c))
        t[47] = self.clock_opacity & 255
        t[48] = 1 if self.clock_all_visible else 0
        for i, v in enumerate([self.time_font, self.date_font, self.temp_font, self.clock_size]):
            t[49 + i] = (v - 1 if v > 0 else v) & 255
        t[53] = self.show_order & 255
        return bytes(t)


# -- text rendering -------------------------------------------------------------------
def _font(height: int, text: str, font_path: str, max_width: int | None = None):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    size = height
    while size > 5:
        f = ImageFont.truetype(font_path, size)
        l, t, r, b = probe.textbbox((0, 0), text, font=f)
        if b - t <= height and (max_width is None or r - l <= max_width):
            return f, (l, t, r, b)
        size -= 1
    return f, (l, t, r, b)


def text_mask(text: str, height: int, font_path: str = DEFAULT_FONT, max_width: int | None = None,
              threshold: int = 110) -> Image.Image:
    f, (l, t, r, b) = _font(height, text, font_path, max_width)
    m = Image.new("L", (max(1, r - l), height), 0)
    ImageDraw.Draw(m).text((-l, (height - (b - t)) // 2 - t), text, fill=255, font=f)
    return m.point(lambda v: 255 if v >= threshold else 0)


def _regions(cfg: Config, layout: str):
    if layout == "panels":
        return [(p["x"], p["width"]) for p in cfg.panels()]
    return [(0, cfg.width)]


def render_static(cfg: Config, text: str, color="ff0000", background="000000", layout: str = "panels",
                  font_path: str = DEFAULT_FONT, align: str = "center") -> Image.Image:
    """layout 'panels': the text on every physical panel; 'span': once across the whole display."""
    fg, bg = parse_color(color), parse_color(background)
    img = Image.new("RGB", (cfg.width, cfg.height), bg)
    for x0, w in _regions(cfg, layout):
        m = text_mask(text, cfg.height, font_path, max_width=w)
        x = {"left": 0, "right": w - m.width}.get(align, (w - m.width) // 2)
        layer = Image.new("RGB", (w, cfg.height), bg)
        layer.paste(Image.new("RGB", m.size, fg), (x, 0), m)
        img.paste(layer, (x0, 0))
    return img


def render_scroll(cfg: Config, text: str, color="ff0000", background="000000", layout: str = "panels",
                  step: int = 1, font_path: str = DEFAULT_FONT, gap: int = 0) -> list:
    """Frames for right-to-left scrolling text on every panel ('panels') or across the display ('span')."""
    fg, bg = parse_color(color), parse_color(background)
    m = text_mask(text, cfg.height, font_path)
    regions = _regions(cfg, layout)
    longest = max(w for _, w in regions)
    colour = Image.new("RGB", m.size, fg)
    frames = []
    for off in range(0, longest + m.width + gap, step):
        img = Image.new("RGB", (cfg.width, cfg.height), bg)
        for x0, w in regions:
            layer = Image.new("RGB", (w, cfg.height), bg)
            layer.paste(colour, (w - off, 0), m)
            img.paste(layer, (x0, 0))
        frames.append(img)
    return frames


def fit_image(cfg: Config, path: str) -> Image.Image:
    src = Image.open(path).convert("RGB")
    src.thumbnail((cfg.width, cfg.height))
    img = Image.new("RGB", (cfg.width, cfg.height))
    img.paste(src, ((cfg.width - src.width) // 2, (cfg.height - src.height) // 2))
    return img


def merge_frames(images: list, durations) -> list:
    """Merge identical consecutive images; returns [(image, duration)], duration capped at 65535 units."""
    if isinstance(durations, int):
        durations = [durations] * len(images)
    out = []
    for im, d in zip(images, durations):
        if out and out[-1][0].tobytes() == im.tobytes() and out[-1][1] + d <= 65535:
            out[-1] = (out[-1][0], out[-1][1] + d)
        else:
            out.append((im, d))
    return out


def build_spot(cfg: Config, images: list, duration, name: str = "Spot", special: Special | None = None,
               compress: bool = True, merge: bool = True) -> dict:
    """duration: units of 10 ms, one value for all frames or a list per frame."""
    trailer = special.trailer() if special else None
    size = special_buffer_size(cfg) if special else 0
    pairs = merge_frames(images, duration) if merge else list(
        zip(images, duration if isinstance(duration, list) else [duration] * len(images)))
    frames = [frame_packet(i, compose(im, cfg), d, trailer, size, compress) for i, (im, d) in enumerate(pairs)]
    return {"name": name, "frames": frames, "images": [im for im, _ in pairs]}


def preview_sheet(images: list, path: str, max_frames: int = 6, scale: int = 3):
    pick = images[:: max(1, len(images) // max_frames)][:max_frames]
    w, h = pick[0].size
    sheet = Image.new("RGB", (w, (h + 2) * len(pick)), (40, 40, 40))
    for i, im in enumerate(pick):
        sheet.paste(im, (0, i * (h + 2)))
    sheet.resize((w * scale, sheet.height * scale), Image.NEAREST).save(path)
    return path


FONTS_BLOB = os.environ.get("KO5G_VENDOR_FONTS",
                            os.path.join(os.path.dirname(__file__), "assets", "fonts_color.bin"))


def vendor_font_blob() -> bytes:
    """Fonts the vendor app uploads (assets/fonts/color.bin: 4-byte length + data).
    Not distributed with this project; extract it from your own copy of the vendor app with
    tools/extract_vendor_fonts.py."""
    if not os.path.exists(FONTS_BLOB):
        raise FileNotFoundError(f"vendor font file not found ({FONTS_BLOB}); "
                                "see tools/extract_vendor_fonts.py")
    with open(FONTS_BLOB, "rb") as f:
        n = int.from_bytes(f.read(4), "big")
        return f.read(n)
