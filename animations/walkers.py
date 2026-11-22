"""Little pixel people walking across the display (seamless loop).

    .venv/bin/python animations/walkers.py [--preview out.png] [--dry-run]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402

from ko5g import Display  # noqa: E402
from ko5g.frames import build_spot, preview_sheet  # noqa: E402

# 7 x 13 sprites, facing right. H = hair/head, # = body colour, s = skin, . = transparent
WALK = [
    """
..HHH..
.Hsss..
..sss..
...s...
.#####.
#.###.#
s.###.s
..###..
..#.#..
.#...#.
.#...#.
#.....#
#......
""",
    """
..HHH..
.Hsss..
..sss..
...s...
..###..
.#####.
.s###s.
..###..
..#.#..
..#.#..
..#.#..
..#.#..
..#.#..
""",
    """
..HHH..
.Hsss..
..sss..
...s...
.#####.
#.###.#
s.###.s
..###..
..#.#..
.#...#.
.#...#.
#.....#
......#
""",
    """
..HHH..
.Hsss..
..sss..
...s...
..###..
.#####.
.s###s.
..###..
..#.#..
..#.#..
..#.#..
..#.#..
..#.#..
""",
]
JUMP = """
s.HHH.s
#Hsss.#
#.sss.#
.#.s.#.
..###..
..###..
..###..
..###..
..#.#..
.#...#.
#.....#
.......
.......
"""

SKIN = (255, 190, 140)
PEOPLE = [  # (start x, body colour, hair colour, direction, jumper)
    (0, (255, 0, 0), (120, 60, 0), 1, False),
    (60, (0, 120, 255), (255, 220, 0), 1, False),
    (130, (0, 220, 0), (60, 30, 0), 1, True),
    (200, (255, 150, 0), (200, 0, 200), 1, False),
    (250, (200, 0, 255), (255, 255, 255), 1, False),
]


def parse(s):
    return [row for row in s.strip("\n").split("\n")]


def draw(img, sprite, x0, y0, body, hair, flip):
    px = img.load()
    w, h = img.size
    rows = parse(sprite)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = {"#": body, "H": hair, "s": SKIN}[ch]
            xx = x0 + (len(row) - 1 - x if flip else x)
            yy = y0 + y
            if 0 <= yy < h:
                px[xx % w, yy] = c


def frames(width=288, height=16):
    out = []
    jump_curve = [0, -1, -2, -3, -3, -3, -2, -1, 0]
    for t in range(width):
        img = Image.new("RGB", (width, height))
        for i, (sx, body, hair, d, jumper) in enumerate(PEOPLE):
            x = (sx + t * d) % width
            y = height - 13
            if jumper and (t // 9) % 4 == 3:
                draw(img, JUMP, x, y + jump_curve[t % 9], body, hair, d < 0)
            else:
                draw(img, WALK[(t // 3 + i) % 4], x, y, body, hair, d < 0)
        out.append(img)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    ap.add_argument("--duration", type=int, default=5, help="10 ms units per frame")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    imgs = frames()
    if a.preview:
        preview_sheet(imgs, a.preview, max_frames=4, scale=4)
        print("preview", a.preview)
    if a.dry_run:
        return
    d = Display()
    print(d.upload([build_spot(d.config, imgs, a.duration, "Walkers")]).to_dict())


if __name__ == "__main__":
    main()
