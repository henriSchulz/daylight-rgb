"""Command line interface.

    python -m ko5g [--display IP] status
    python -m ko5g text "Hello" [--color ff0000] [--scroll] [--layout panels|span]
    python -m ko5g scene scenes/race.scene.json
    python -m ko5g image picture.png [--duration 300]
    python -m ko5g time
    python -m ko5g switch next|prev|goto [--spot N] [--frame N]
    python -m ko5g mode auto|manual_spots [--repeat 1 ...]

The display address comes from --display or the KO5G_HOST environment variable.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import Display
from .scene import load


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ko5g", description="Control a Ko5G colour LED display.")
    ap.add_argument("--display", help="display IP or host name (default: $KO5G_HOST)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show configuration, composition and position")

    t = sub.add_parser("text", help="show a text (replaces the content)")
    t.add_argument("text")
    t.add_argument("--color", default="ff0000")
    t.add_argument("--background", default="000000")
    t.add_argument("--scroll", action="store_true")
    t.add_argument("--layout", choices=["panels", "span"], default="panels")
    t.add_argument("--step", type=int, default=1)
    t.add_argument("--duration", type=int, help="10 ms units per frame")

    s = sub.add_parser("scene", help="render a .scene.json file and send it")
    s.add_argument("file")

    i = sub.add_parser("image", help="show an image file (scaled to fit)")
    i.add_argument("file")
    i.add_argument("--duration", type=int, default=100)

    sub.add_parser("time", help="set the display clock to the computer's time")

    w = sub.add_parser("switch", help="switch spot/frame")
    w.add_argument("action", choices=["next", "prev", "next-frame", "prev-frame", "goto"])
    w.add_argument("--spot", type=int, default=0)
    w.add_argument("--frame", type=int, default=0)

    m = sub.add_parser("mode", help="set the playback mode")
    m.add_argument("mode", choices=["auto", "manual_spots", "manual_frames", "daily", "weekly"])
    m.add_argument("--repeat", type=int, nargs="*", help="auto mode: repeats per spot")

    a = ap.parse_args(argv)
    try:
        d = Display(a.display)
    except ValueError as e:
        ap.error(str(e))

    if a.cmd == "status":
        print(json.dumps(d.info(), indent=2))
    elif a.cmd == "text":
        comp = d.upload([d.make_text_spot(a.text, color=a.color, background=a.background, scroll=a.scroll,
                                          layout=a.layout, step=a.step, duration=a.duration)])
        print(comp.to_dict())
    elif a.cmd == "scene":
        print(d.play_scene(load(a.file)).to_dict())
    elif a.cmd == "image":
        print(d.upload([d.make_image_spot(a.file, a.duration)]).to_dict())
    elif a.cmd == "time":
        d.set_time()
        print("clock set")
    elif a.cmd == "switch":
        fn = {"next": d.next_spot, "prev": d.prev_spot, "next-frame": d.next_frame, "prev-frame": d.prev_frame}
        r = fn[a.action]() if a.action in fn else d.goto(a.spot, a.frame)
        print("reply", r[:2].hex(" "))
    elif a.cmd == "mode":
        d.set_mode(a.mode, a.repeat)
        print("mode set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
