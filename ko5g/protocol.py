"""Low-level protocol for RGB Technology colour LED controllers ("Ko5G", protocol v5).

Recovered from the vendor Android apps "RGB Switcher" (pl.RGBTechnology.Switcher 1.17)
and "RGB Cross" (pl.rgbtechnology.rgbcross 1.18). Verified on a 288x16 display.

Every command is one TCP connection to port 2101:
    b"Ko5G" + command byte + payload  ->  reply
Short replies: aa aa = OK, c8 c8 = unknown command, cc cc = rejected.
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from datetime import datetime

HEADER = b"Ko5G"
DEFAULT_PORT = 2101

# command bytes (vendor table "ColorCommand103")
CMD_SEND_CONFIG = 0x01
CMD_RETURN_CONFIG = 0x02
CMD_SEND_FONTS = 0x03
CMD_CHANGE_DATETIME = 0x04
CMD_SWITCH_SPOT_FRAME = 0x06
CMD_NEW_COMP = 0x07
CMD_RETURN_COMP = 0x08
CMD_CHANGE_COMP_MODE = 0x09
CMD_ADD_SPOT = 0x0B
CMD_SHOW_ADDRESSES = 0x0C
CMD_RETURN_POSITION = 0x0D
CMD_SENDING_RETRY = 0x10
CMD_CHANGE_BRIGHTNESS = 0x14

REPLY_OK = b"\xaa\xaa"
REPLY_UNKNOWN = b"\xc8\xc8"
REPLY_REJECTED = b"\xcc\xcc"

# composition modes (Localization$displayMode ordinals)
MODE_AUTO = 0          # spots one after another, each `repeat` times
MODE_DAILY = 1         # each spot starts at hh:mm every day
MODE_WEEKLY = 2        # each spot starts at hh:mm per weekday
MODE_MANUAL_SPOTS = 3  # one spot loops until switched
MODE_MANUAL_FRAMES = 4 # single frames switched by hand
MODE_NAMES = {0: "auto", 1: "daily", 2: "weekly", 3: "manual_spots", 4: "manual_frames"}

# SwitchSpotFrame sub-commands
SWITCH_NEXT_SPOT, SWITCH_PREV_SPOT, SWITCH_NEXT_FRAME, SWITCH_PREV_FRAME, SWITCH_GOTO = 1, 2, 3, 4, 0

# board geometry tables (ImageGenerator, colour)
_PIXEL_W = [16, 16, 16, 16, 32, 32, 32, 0]
_PIXEL_H = [8, 8, 16, 16, 16, 32, 32, 0]
_ADDR_W = [1, 1, 1, 1, 2, 2, 2, 0]
_ADDR_H = [1, 1, 2, 2, 2, 4, 4, 0]
SHAPES = {0: "rectangle", 1: "rectangle_double", 2: "cross", 3: "cross_double"}


class ProtocolError(RuntimeError):
    pass


@dataclass
class Config:
    """Parsed 709-byte colour configuration (Module.getConfigurationArray / SetParametersColor)."""
    raw: bytes
    width: int
    height: int
    board_type: int
    shape: int
    addresses: list            # [port][16] 24-bit module addresses
    port_map: bytes            # 128 entries: fragment index -> port+1 (0 = none)
    brightness: bytes          # 173 bytes: 7x24 levels, mode, 2 limits, 2 values

    @property
    def fragment_size(self):
        return _PIXEL_W[self.board_type] // _ADDR_W[self.board_type], _PIXEL_H[self.board_type] // _ADDR_H[self.board_type]

    @property
    def fragment_columns(self):
        return self.width // self.fragment_size[0]

    def fragment_order(self):
        """Fragments in transmission order: grouped by port, ascending index, wired only."""
        fw, fh = self.fragment_size
        n = self.fragment_columns * (self.height // fh)
        per_port = [[] for _ in range(8)]
        for idx in range(n):
            if self.port_map[idx]:
                per_port[self.port_map[idx] - 1].append(idx)
        order = []
        for p in range(8):
            for k, idx in enumerate(per_port[p]):
                if k < 16 and self.addresses[p][k] > 0:
                    order.append(idx)
        return order

    def panels(self):
        """Physical sub-displays: runs of fragment columns on the same port in the first row."""
        fw, _ = self.fragment_size
        cols = self.fragment_columns
        pm = self.port_map[:cols]
        out, start = [], 0
        for c in range(1, cols + 1):
            if c == cols or pm[c] != pm[start]:
                if pm[start]:
                    out.append({"x": start * fw, "width": (c - start) * fw, "port": pm[start]})
                start = c
        return out

    @classmethod
    def parse(cls, raw: bytes) -> "Config":
        if len(raw) < 689:
            raise ProtocolError(f"config too short ({len(raw)} B)")
        addresses = [[int.from_bytes(raw[4 + p * 48 + 3 * k:7 + p * 48 + 3 * k], "big") for k in range(16)] for p in range(8)]
        return cls(raw=bytes(raw), width=raw[1] * 16, height=raw[0] * 8, board_type=raw[2], shape=raw[3],
                   addresses=addresses, port_map=bytes(raw[388:516]), brightness=bytes(raw[516:689]))

    def to_dict(self):
        return {"width": self.width, "height": self.height, "board_type": self.board_type,
                "shape": SHAPES.get(self.shape, self.shape), "fragment_size": self.fragment_size,
                "panels": self.panels(), "wired_fragments": len(self.fragment_order())}


@dataclass
class Composition:
    """Parsed ReturnComp reply (protocol v5, 10866 B)."""
    raw: bytes
    spot_count: int
    mode: int
    frames_per_spot: list = field(default_factory=list)

    @classmethod
    def parse(cls, raw: bytes) -> "Composition":
        if len(raw) < 6:
            raise ProtocolError(f"composition reply too short ({len(raw)} B): {raw.hex(' ')}")
        n = int.from_bytes(raw[1:3], "big")
        frames = [int.from_bytes(raw[4 + 2 * i:6 + 2 * i], "big") for i in range(min(n, 512))]
        return cls(raw=bytes(raw), spot_count=n, mode=raw[3], frames_per_spot=frames)

    def to_dict(self):
        return {"spot_count": self.spot_count, "mode": MODE_NAMES.get(self.mode, self.mode),
                "frames_per_spot": self.frames_per_spot}


class Connection:
    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.host, self.port, self.timeout = host, port, timeout

    # -- transport -------------------------------------------------------
    def exchange(self, chunks, wait: float = 4.0, quiet_after: float = 0.4, progress=None,
                 expect: int | None = None) -> bytes:
        """One TCP connection: send bytes (or a list of byte chunks), collect the reply.
        Returns as soon as `expect` bytes arrived, otherwise after `quiet_after` s of silence."""
        if isinstance(chunks, (bytes, bytearray)):
            chunks = [bytes(chunks)]
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            s.settimeout(60)
            for i, c in enumerate(chunks):
                s.sendall(c)
                if progress:
                    progress(i + 1, len(chunks))
            s.settimeout(0.05 if expect else 0.2)
            buf, t0, last = b"", time.time(), time.time()
            while time.time() - t0 < wait:
                try:
                    d = s.recv(65536)
                    if not d:
                        break
                    buf += d
                    last = time.time()
                    if expect and len(buf) >= expect:
                        break
                except socket.timeout:
                    if buf and time.time() - last > quiet_after:
                        break
            return buf
        finally:
            s.close()

    def command(self, code: int, payload: bytes = b"", total_len: int | None = None, retries: int = 2, **kw) -> bytes:
        body = HEADER + bytes([code]) + payload
        if total_len is not None:
            body = body.ljust(total_len, b"\x00")
        for attempt in range(retries + 1):
            try:
                return self.exchange(body, **kw)
            except (ConnectionResetError, ConnectionRefusedError, socket.timeout):
                if attempt == retries:
                    raise
                time.sleep(1.0 + attempt)

    @staticmethod
    def expect_ok(reply: bytes, what: str):
        if reply[:2] != REPLY_OK:
            raise ProtocolError(f"{what}: device replied {reply[:8].hex(' ') or 'nothing'}")
        return reply

    # -- read ---------------------------------------------------------------
    def _read(self, code: int, expect: int, min_len: int, tries: int = 10) -> bytes:
        """Read command with retries: the controller sends nothing while it is busy writing."""
        r = b""
        for _ in range(tries):
            r = self.command(code, expect=expect, wait=2.0)
            if len(r) >= min_len:
                return r
            time.sleep(0.5)
        return r

    def read_config(self) -> Config:
        return Config.parse(self._read(CMD_RETURN_CONFIG, 709, 689))

    def read_composition(self) -> Composition:
        return Composition.parse(self._read(CMD_RETURN_COMP, 10866, 6))

    def read_position(self) -> dict:
        r = self._read(CMD_RETURN_POSITION, 63, 10)
        if len(r) < 10:
            raise ProtocolError(f"position reply {r.hex(' ')}")
        return {"spot": int.from_bytes(r[0:2], "big"), "frame": int.from_bytes(r[2:4], "big"),
                "raw": r[:16].hex(" ")}

    # -- simple writes ------------------------------------------------------
    def set_datetime(self, dt: datetime | None = None):
        dt = dt or datetime.now()
        p = bytes([dt.hour, dt.minute, dt.second, dt.weekday(), dt.year % 100 or 1, dt.month, dt.day])
        return self.expect_ok(self.command(CMD_CHANGE_DATETIME, p, expect=2), "set_datetime")

    def write_config(self, raw: bytes):
        if len(raw) != 709:
            raise ValueError("colour config must be 709 bytes")
        return self.expect_ok(self.command(CMD_SEND_CONFIG, raw, expect=2), "write_config")

    def write_brightness_block(self, block: bytes):
        """173-byte block: 168 hourly levels (Mon..Sun x 0..23), mode, 2 limits, 2 values."""
        if len(block) != 173:
            raise ValueError("brightness block must be 173 bytes")
        return self.expect_ok(self.command(CMD_CHANGE_BRIGHTNESS, block, total_len=5 + 193, expect=2), "brightness")

    def send_fonts(self, font_blob: bytes):
        return self.expect_ok(self.command(CMD_SEND_FONTS, font_blob, wait=20.0, expect=2), "send_fonts")

    def show_addresses(self, on: bool):
        return self.command(CMD_SHOW_ADDRESSES, bytes([1 if on else 0]), expect=2)

    def switch(self, sub: int, spot: int = 0, frame: int = 0) -> bytes:
        """SwitchSpotFrame: sub 1 next spot, 2 prev spot, 3 next frame, 4 prev frame, 0 goto."""
        p = bytes([sub]) + spot.to_bytes(2, "big") + frame.to_bytes(2, "big")
        return self.command(CMD_SWITCH_SPOT_FRAME, p, expect=2)

    # -- composition ------------------------------------------------------------
    def change_comp_mode(self, mode: int, spot_count: int, params=None, disabled=None):
        """ChangeCompMode (7736 B). params per spot: auto -> repeat count, daily -> (h, m),
        weekly -> [(h, m) x 7] (Mon..Sun, None = off). disabled: list of bools."""
        p = bytearray(7731)
        p[0] = mode
        for i in range(512):
            p[7169 + i] = 7
        for i in range(spot_count):
            off = bool(disabled and disabled[i])
            p[7169 + i] = (int(off) << 4) | ((2 if off else 0) << 2) | (2 if off else 0)
        params = params or []
        for i, v in enumerate(params[:spot_count]):
            if mode == MODE_AUTO:
                p[1 + 2 * i:3 + 2 * i] = int(v or 1).to_bytes(2, "big")
            elif mode == MODE_DAILY and v:
                p[1 + 2 * i], p[2 + 2 * i] = v[0], v[1]
            elif mode == MODE_WEEKLY and v:
                for d, hm in enumerate(v[:7]):
                    o = 1 + 2 * i + d * 1024
                    p[o], p[o + 1] = (hm if hm else (255, 255))
        return self.expect_ok(self.command(CMD_CHANGE_COMP_MODE, bytes(p), expect=2), "change_comp_mode")

    def upload(self, cfg: Config, spots, mode: int = MODE_MANUAL_SPOTS, progress=None, log=print):
        """Replace the whole composition. spots: list of dicts {name, frames: [bytes per frame]}
        where each frame is an already composed frame packet (see frames.py)."""
        p = bytearray(8759)
        p[0], p[1] = cfg.height // 8, cfg.width // 16
        p[2:4] = len(spots).to_bytes(2, "big")
        p[4] = mode
        for i, s in enumerate(spots):
            p[5 + 2 * i:7 + 2 * i] = len(s["frames"]).to_bytes(2, "big")
        self.expect_ok(self.command_until_ok(CMD_NEW_COMP, bytes(p), expect=2), "new_comp")
        log(f"new composition: {len(spots)} spot(s)")
        for idx, s in enumerate(spots):
            h = bytearray(70)
            for i, ch in enumerate(s.get("name", f"Spot {idx + 1}").encode("ascii", "replace")[:34]):
                h[2 * i] = ch
            h[68:70] = idx.to_bytes(2, "big")
            self.expect_ok(self.command_until_ok(CMD_ADD_SPOT, bytes(h), expect=2), f"add_spot {idx}")
            reply = self.exchange(s["frames"], wait=60.0, expect=2,
                                  progress=(lambda i, n, idx=idx: progress(idx, i, n)) if progress else None)
            self.expect_ok(reply, f"frames of spot {idx}")
            log(f"spot {idx + 1}: {len(s['frames'])} frame(s) stored")
        self.wait_ready()
        return self.read_composition()

    def wait_ready(self, timeout: float = 30.0):
        """The controller ignores commands while it writes to flash; poll ReturnPosition until it answers."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if len(self.command(CMD_RETURN_POSITION, wait=1.0, retries=0, expect=63)) >= 10:
                    return True
            except OSError:
                pass
            time.sleep(0.3)
        raise ProtocolError("display not ready (busy for more than %.0f s)" % timeout)

    def command_until_ok(self, code: int, payload: bytes, tries: int = 5, **kw) -> bytes:
        r = b""
        for _ in range(tries):
            r = self.command(code, payload, **kw)
            if r[:2] == REPLY_OK:
                return r
            time.sleep(1.0)
        return r
