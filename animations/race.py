"""A small car race across all three panels (original pixel cars, side view).

    .venv/bin/python animations/race.py [--preview out.png] [--dry-run] [--duration 5]
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402

from ko5g import Display  # noqa: E402
from ko5g.frames import build_spot, preview_sheet, text_mask  # noqa: E402

W, H = 288, 16
FINISH = 278

# 12 x 5 car facing right. # body, w window, O wheel, h headlight, . transparent
CAR = """
....####....
...#ww#w#...
.##########h
############
..OO....OO..
"""
CARS = [  # name, colour, lane y, keyframes (frame, x) of the front-left corner
    ("ROT", (230, 0, 0), 0, [(0, 2), (20, 30), (60, 95), (100, 175), (125, 230), (140, 285)]),
    ("BLAU", (0, 110, 255), 5, [(0, 2), (20, 38), (60, 115), (100, 190), (125, 232), (140, 270)]),
    ("GELB", (255, 210, 0), 10, [(0, 2), (20, 26), (60, 100), (100, 170), (125, 215), (140, 255)]),
]


def smooth(keys, t):
    """Cosine interpolation between keyframes; continues with the last speed afterwards."""
    if t >= keys[-1][0]:
        (t0, x0), (t1, x1) = keys[-2], keys[-1]
        return x1 + (t - t1) * (x1 - x0) / (t1 - t0)
    for (t0, x0), (t1, x1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            u = (1 - math.cos(u * math.pi)) / 2
            return x0 + (x1 - x0) * u
    return keys[0][1]


def draw_car(px, x0, y0, colour, t, moving):
    rows = CAR.strip("\n").split("\n")
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "#":
                c = colour
            elif ch == "w":
                c = (150, 220, 255)
            elif ch == "h":
                c = (255, 255, 180)
            else:  # wheel: spinning highlight
                c = (200, 200, 200) if moving and (x + t) % 2 else (70, 70, 70)
            xx, yy = int(x0) + x, y0 + y
            if 0 <= xx < W and 0 <= yy < H:
                px[xx, yy] = c


def road(px, scroll=0):
    for x in range(W):
        if (x + scroll) % 6 < 3:
            px[x, 15] = (60, 60, 60)
    for y in range(0, 15):          # finish line, checkered
        for dx in range(2):
            px[FINISH + dx, y] = (255, 255, 255) if (y // 2 + dx) % 2 == 0 else (30, 30, 30)
    for y in range(0, 15):          # start line
        px[15, y] = (120, 120, 120)


def text(img, s, x0, w, colour):
    m = text_mask(s, H, max_width=w)
    img.paste(Image.new("RGB", m.size, colour), (x0 + (w - m.width) // 2, 0), m)


def build():
    frames = []
    # countdown: cars waiting at the start, engines puffing
    for label, colour, n in (("3", (255, 0, 0), 14), ("2", (255, 0, 0), 14), ("1", (255, 160, 0), 14),
                              ("GO!", (0, 255, 0), 10)):
        for i in range(n):
            img = Image.new("RGB", (W, H))
            px = img.load()
            road(px)
            for _, c, lane, keys in CARS:
                draw_car(px, keys[0][1] + (i % 2 if label != "GO!" else 0) * 0, lane, c, i, False)
                if i % 4 < 2:
                    px[keys[0][1] - 1, lane + 3] = (110, 110, 110)
            # countdown on panels 2 and 3 (sky area above the cars is too small)
            img.paste(Image.new("RGB", (160, H)), (128, 0))
            text(img, label, 192, 96, colour)
            frames.append(img)
    # the race
    winner = None
    t = 0
    while True:
        img = Image.new("RGB", (W, H))
        px = img.load()
        road(px)
        done = True
        for name, colour, lane, keys in CARS:
            x = smooth(keys, t)
            moving = x < W
            if moving:
                done = False
            draw_car(px, x, lane, colour, t, True)
            if t % 3 == 0 and 0 <= int(x) - 2 < W:
                px[int(x) - 2, lane + 3] = (120, 120, 120)
            if winner is None and x + 11 >= FINISH:
                winner = (name, colour)
        frames.append(img)
        t += 1
        if done or t > 200:
            break
    # winner screen
    name, colour = winner
    for i in range(50):
        img = Image.new("RGB", (W, H))
        px = img.load()
        text(img, "SIEG!", 0, 128, (255, 255, 255) if (i // 5) % 2 else (255, 220, 0))
        draw_car(px, 154, 6, colour, i, True)
        for k in range(6):  # sparkles
            sx = 132 + (k * 37 + i * 3) % 56
            sy = (k * 5 + i) % 6
            if (i + k) % 3 == 0:
                px[sx, sy] = (255, 255, 120)
        text(img, name, 192, 96, colour)
        frames.append(img)
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    ap.add_argument("--duration", type=int, default=5, help="10 ms units per frame")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    imgs = build()
    print(len(imgs), "frames")
    if a.preview:
        preview_sheet(imgs, a.preview, max_frames=10, scale=3)
        print("preview", a.preview)
    if a.dry_run:
        return
    d = Display()
    print(d.upload([build_spot(d.config, imgs, a.duration, "Race")]).to_dict())


if __name__ == "__main__":
    main()
