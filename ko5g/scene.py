"""Reference interpreter for the ko5g-scene format (docs/scene-format.md)."""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_JS = os.path.join(ROOT, "web", "font5x8.js")
GLYPH_H = 8
SPACE_W = 3


class SceneError(ValueError):
    pass


# -- pixel font (single source of truth: web/font5x8.js) --------------------------------
_glyph_src: dict | None = None
_glyph_cache: dict = {}


def _load_font():
    global _glyph_src
    if _glyph_src is None:
        _glyph_src = {}
        pat = re.compile(r"""^\s*'((?:\\.|[^'\\])+)'\s*:\s*'([^']*)'\s*,?\s*$""")
        with open(FONT_JS, encoding="utf-8") as f:
            for line in f:
                m = pat.match(line)
                if m:
                    key = re.sub(r"\\(.)", r"\1", m.group(1))
                    _glyph_src[key] = m.group(2)
    return _glyph_src


def _glyph(ch: str):
    if ch in _glyph_cache:
        return _glyph_cache[ch]
    if ch == " ":
        g = (SPACE_W, [[0] * SPACE_W for _ in range(GLYPH_H)])
    else:
        src = _load_font()
        s = src.get(ch) or src.get(unicodedata.normalize("NFD", ch)[0]) or src["?"]
        rows = s.split(" ")
        cols = [x for r in rows for x in range(5) if x < len(r) and r[x] == "#"]
        lo, hi = (min(cols), max(cols)) if cols else (0, -1)
        w = hi - lo + 1
        px = [[0] * max(w, 0) for _ in range(GLYPH_H)]
        for y, r in enumerate(rows[:GLYPH_H]):
            for x in range(w):
                if lo + x < len(r) and r[lo + x] == "#":
                    px[y][x] = 1
        g = (w, px)
    _glyph_cache[ch] = g
    return g


def text_bitmap(text: str, scale: int = 2):
    """Returns (w, h, set of lit (x, y))."""
    glyphs = [_glyph(c) for c in text]
    w1 = sum(g[0] for g in glyphs) + max(0, len(glyphs) - 1)
    lit = set()
    cx = 0
    for gw, px in glyphs:
        for y in range(GLYPH_H):
            for x in range(gw):
                if px[y][x]:
                    for dy in range(scale):
                        for dx in range(scale):
                            lit.add(((cx + x) * scale + dx, y * scale + dy))
        cx += gw + 1
    return w1 * scale, GLYPH_H * scale, lit


# -- values ---------------------------------------------------------------------------
def value(v, t: int, default=0):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return math.floor(v + 0.5)
    if isinstance(v, dict) and "keys" in v:
        keys = v["keys"]
        if not keys:
            return default
        rep = v.get("repeat", 0) or 0
        if rep > 0:
            t = t % rep
        if t <= keys[0][0]:
            r = keys[0][1]
        elif t >= keys[-1][0]:
            r = keys[-1][1]
        else:
            r = keys[-1][1]
            for (ta, va), (tb, vb) in zip(keys, keys[1:]):
                if ta <= t < tb:
                    ease = v.get("ease", "linear")
                    u = (t - ta) / (tb - ta)
                    if ease == "step":
                        r = va
                    else:
                        if ease == "smooth":
                            u = (1 - math.cos(math.pi * u)) / 2
                        r = va + (vb - va) * u
                    break
        return math.floor(r + 0.5)
    raise SceneError(f"invalid value: {v!r}")


# -- renderer -------------------------------------------------------------------------
class Renderer:
    def __init__(self, doc: dict, width: int = 288, height: int = 16, panels=None):
        if doc.get("format") != "ko5g-scene" or doc.get("version") != 1:
            raise SceneError("not a ko5g-scene v1 file")
        self.doc, self.W, self.H = doc, width, height
        self.panels = panels or [{"x": 0, "width": width}]
        self.palette = doc.get("colors", {})
        self.sprites = doc.get("sprites", {})

    def color(self, c):
        if isinstance(c, str) and c in self.palette:
            c = self.palette[c]
        if not (isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)):
            raise SceneError(f"unknown colour {c!r}")
        return tuple(bytes.fromhex(c[1:]))

    def fps(self, scene):
        return scene.get("fps", self.doc.get("fps", 20))

    def duration_units(self, scene):
        return max(1, math.floor(100 / self.fps(scene) + 0.5))

    def frames(self, scene):
        n = int(scene["frames"])
        return [self.render(scene, t) for t in range(n)]

    # one frame
    def render(self, scene, t: int) -> Image.Image:
        img = Image.new("RGB", (self.W, self.H), self.color(scene.get("background", "#000000")))
        px = img.load()
        for layer in scene["layers"]:
            if not self._visible(layer, t):
                continue
            clip = layer.get("clip", [0, 0, self.W, self.H])
            wrap = bool(layer.get("wrap"))

            def put(x, y, c, clip=clip, wrap=wrap):
                if wrap:
                    x %= self.W
                if clip[0] <= x < clip[2] and clip[1] <= y < clip[3] and 0 <= x < self.W and 0 <= y < self.H:
                    px[x, y] = c

            getattr(self, "_" + layer["type"])(layer, t, put)
        return img

    def _visible(self, layer, t):
        f, to = layer.get("from", 0), layer.get("to")
        if t < f or (to is not None and t >= to):
            return False
        if "blink" in layer:
            on, off = layer["blink"]
            if (t - f) % (on + off) >= on:
                return False
        return value(layer.get("visible"), t, 1) != 0

    def _sprite(self, L, t, put):
        sp = self.sprites.get(L["sprite"])
        if sp is None:
            raise SceneError(f"unknown sprite {L['sprite']!r}")
        frames = sp["frames"]
        if "cycle" in L:
            cy = L["cycle"]
            seq = cy["seq"]
            idx = seq[((t + cy.get("offset", 0)) // max(1, cy.get("every", 1))) % len(seq)]
        else:
            idx = value(L.get("frame"), t, 0)
        rows = frames[idx % len(frames)]
        cmap = {**sp.get("colors", {}), **L.get("colors", {})}
        x0, y0 = value(L.get("x"), t), value(L.get("y"), t)
        flip = value(L.get("flip"), t) != 0
        flash = self.color(L.get("flash_color", "#ffffff")) if value(L.get("flash"), t) else None
        resolved = {}
        for y, row in enumerate(rows):
            w = len(row)
            for x, ch in enumerate(row):
                if ch in ". ":
                    continue
                if ch not in resolved:
                    if ch not in cmap:
                        raise SceneError(f"sprite {L['sprite']!r}: no colour for {ch!r}")
                    resolved[ch] = self.color(cmap[ch])
                put(x0 + (w - 1 - x if flip else x), y0 + y, flash or resolved[ch])

    def _region(self, L):
        if "panel" in L:
            p = self.panels[min(len(self.panels), int(L["panel"])) - 1]
            return p["x"], p["width"]
        if "region" in L:
            return L["region"][0], L["region"][1]
        return 0, self.W

    def _text(self, L, t, put):
        w, h, lit = text_bitmap(str(L["text"]), int(L.get("scale", 2)))
        x0, rw = self._region(L)
        align = L.get("align", "center")
        x = x0 if align == "left" else x0 + rw - w if align == "right" else x0 + (rw - w) // 2
        x += value(L.get("x"), t)
        y = (self.H - h) // 2 + value(L.get("y"), t)
        c = self.color(L.get("color", "#ffffff"))
        for lx, ly in lit:
            put(x + lx, y + ly, c)

    def _rect(self, L, t, put):
        x, y, w, h = (value(L.get(k), t) for k in ("x", "y", "w", "h"))
        c = self.color(L["color"])
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                put(xx, yy, c)

    def _bar(self, L, t, put):
        x, y, w, h = (value(L.get(k), t) for k in ("x", "y", "w", "h"))
        v = max(0, min(100, value(L.get("value"), t)))
        filled = math.floor(w * v / 100)
        c = self.color(L["color"])
        back = self.color(L["back"]) if L.get("back") else None
        rtl = L.get("dir", "ltr") == "rtl"
        for i in range(w):
            on = (i >= w - filled) if rtl else (i < filled)
            col = c if on else back
            if col is None:
                continue
            for yy in range(y, y + h):
                put(x + i, yy, col)

    def _pattern(self, L, t, put):
        x, y, w, h = (value(L.get(k), t) for k in ("x", "y", "w", "h"))
        rows = L["rows"]
        cmap = L.get("colors", {})
        off = value(L.get("offset"), t)
        th = len(rows)
        cache = {}
        for j in range(h):
            row = rows[j % th]
            tw = len(row)
            for i in range(w):
                ch = row[(i + off) % tw]
                if ch in ". ":
                    continue
                if ch not in cache:
                    cache[ch] = self.color(cmap[ch])
                put(x + i, y + j, cache[ch])

    def _pixels(self, L, t, put):
        x0, y0 = value(L.get("x"), t), value(L.get("y"), t)
        for px_, py_, c in L["points"]:
            put(x0 + px_, y0 + py_, self.color(c))


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def to_spots(doc: dict, cfg) -> tuple:
    """Render all scenes for a device config -> (spots, mode, params)."""
    from .frames import build_spot
    r = Renderer(doc, cfg.width, cfg.height, cfg.panels())
    spots, repeats = [], []
    for i, sc in enumerate(doc["scenes"]):
        imgs = r.frames(sc)
        spots.append(build_spot(cfg, imgs, r.duration_units(sc), sc.get("name", f"Szene {i + 1}")))
        repeats.append(int(sc.get("repeat", 1)))
    mode = doc.get("mode") or ("auto" if len(spots) > 1 else "manual_spots")
    return spots, mode, (repeats if mode == "auto" else None)
