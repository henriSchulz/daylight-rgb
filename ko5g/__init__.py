"""Control library for RGB Technology "Ko5G" colour LED displays (TCP 2101)."""
from __future__ import annotations

import os
from datetime import datetime

from . import frames as fr
from .protocol import (MODE_AUTO, MODE_DAILY, MODE_MANUAL_FRAMES, MODE_MANUAL_SPOTS, MODE_NAMES, MODE_WEEKLY,
                       SWITCH_GOTO, SWITCH_NEXT_FRAME, SWITCH_NEXT_SPOT, SWITCH_PREV_FRAME, SWITCH_PREV_SPOT,
                       Composition, Config, Connection, ProtocolError)

__all__ = ["Display", "Config", "Composition", "ProtocolError", "MODE_NAMES"]

MODES = {v: k for k, v in MODE_NAMES.items()}


class Display:
    def __init__(self, host: str | None = None, port: int = 2101):
        """host: IP or name of the display; defaults to the KO5G_HOST environment variable."""
        host = host or os.environ.get("KO5G_HOST")
        if not host:
            raise ValueError("no display address: pass host=... or set KO5G_HOST")
        self.conn = Connection(host, port)
        self._cfg: Config | None = None

    # -- state ------------------------------------------------------------------------
    @property
    def config(self) -> Config:
        if self._cfg is None:
            self._cfg = self.conn.read_config()
        return self._cfg

    def info(self) -> dict:
        self._cfg = None
        return {"config": self.config.to_dict(), "composition": self.conn.read_composition().to_dict(),
                "position": self.conn.read_position()}

    # -- content ----------------------------------------------------------------------
    def make_text_spot(self, text: str, color="ff0000", background="000000", scroll: bool = False,
                       layout: str = "panels", step: int = 1, duration: int | None = None,
                       font: str | None = None, name: str | None = None) -> dict:
        cfg = self.config
        font = font or fr.DEFAULT_FONT
        if scroll:
            images = fr.render_scroll(cfg, text, color, background, layout, step, font)
            duration = 3 if duration is None else duration
        else:
            images = [fr.render_static(cfg, text, color, background, layout, font)]
            duration = 100 if duration is None else duration
        return fr.build_spot(cfg, images, duration, name or text[:30])

    def make_image_spot(self, path: str, duration: int = 100, name: str | None = None) -> dict:
        return fr.build_spot(self.config, [fr.fit_image(self.config, path)], duration, name or "Image")

    def make_special_spot(self, special: fr.Special, background=None, duration: int = 100,
                          name: str = "Special") -> dict:
        from PIL import Image
        bg = background if background is not None else Image.new("RGB", (self.config.width, self.config.height))
        return fr.build_spot(self.config, [bg], duration, name, special)

    def upload(self, spots: list, mode: str | int = "manual_spots", params=None, progress=None, log=print):
        """Replace the composition with `spots`; then apply mode/params (repeats or start times)."""
        mode = MODES.get(mode, mode)
        comp = self.conn.upload(self.config, spots, MODE_MANUAL_SPOTS, progress=progress, log=log)
        if mode != MODE_MANUAL_SPOTS or params:
            import time
            self.conn.wait_ready()  # controller is busy right after storing frames
            for attempt in range(3):
                try:
                    self.conn.change_comp_mode(mode, len(spots), params)
                    break
                except ProtocolError:
                    if attempt == 2:
                        raise
                    time.sleep(2)
            comp = self.conn.read_composition()
        return comp

    def play_scene(self, doc: dict, progress=None, log=print):
        """Render a ko5g-scene document (docs/scene-format.md) and upload it."""
        from .scene import to_spots
        spots, mode, params = to_spots(doc, self.config)
        return self.upload(spots, mode, params, progress=progress, log=log)

    def show_text(self, text: str, **kw):
        return self.upload([self.make_text_spot(text, **kw)])

    # -- control ----------------------------------------------------------------------
    def set_mode(self, mode: str | int, params=None, disabled=None):
        mode = MODES.get(mode, mode)
        n = self.conn.read_composition().spot_count
        return self.conn.change_comp_mode(mode, n, params, disabled)

    def next_spot(self):
        return self.conn.switch(SWITCH_NEXT_SPOT)

    def prev_spot(self):
        return self.conn.switch(SWITCH_PREV_SPOT)

    def next_frame(self):
        return self.conn.switch(SWITCH_NEXT_FRAME)

    def prev_frame(self):
        return self.conn.switch(SWITCH_PREV_FRAME)

    def goto(self, spot: int, frame: int = 0):
        """Show spot `spot` (0-based) at frame `frame` (0-based); reply cc cc = does not exist."""
        return self.conn.switch(SWITCH_GOTO, spot, frame)

    def set_time(self, dt: datetime | None = None):
        return self.conn.set_datetime(dt)

    def send_fonts(self):
        return self.conn.send_fonts(fr.vendor_font_blob())

    def show_addresses(self, on: bool = True):
        return self.conn.show_addresses(on)
