"""A small fighting-game style match with two original pixel fighters.

Panel 1 (x 0-127) is the arena with health bars, panels 2 and 3 show the announcements.
    .venv/bin/python animations/fight.py [--preview out.png] [--dry-run] [--duration 6]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402

from ko5g import Display  # noqa: E402
from ko5g.frames import build_spot, preview_sheet, text_mask  # noqa: E402

W, H = 288, 16
ARENA = (0, 128)
SKIN = (255, 190, 140)

# 9 x 13 sprites facing right.  H hair/headband, s skin, # outfit, b belt, . transparent
S = {
    "idle": """
...HHH...
..Hsss...
...sss...
....s....
..#####..
.s#####s.
.s.###.s.
...###...
...bbb...
...#.#...
..#...#..
..#...#..
.##...##.""",
    "step": """
...HHH...
..Hsss...
...sss...
....s....
..#####..
.s#####s.
.s.###.s.
...###...
...bbb...
...#.#...
...#.#...
...#.#...
..##.##..""",
    "punch": """
...HHH...
..Hsss...
...sss...
....s....
..#######
..######s
...###...
...###...
...bbb...
...#.#...
..#...#..
..#...#..
.##...##.""",
    "kick": """
..HHH....
.Hsss....
..sss....
...s.....
.#####...
s#####s..
..###....
..###....
..bbb....
..#.#####
..#....ss
..#......
.##......""",
    "hit": """
.HHH.....
Hsss.....
.sss.....
..s......
.#####...
s#####s..
s.###..s.
..###....
..bbb....
..#.#....
.#...#...
.#...#...
##...##..""",
    "blast": """
...HHH...
..Hsss...
...sss...
....s..ss
..#######
..#######
...###.ss
...###...
...bbb...
...#.#...
..#...#..
.#.....#.
##.....##""",
    "win": """
......s..
...HHHs..
..Hsss#..
...sss#..
....s.#..
..#####..
.s#####..
.s.###...
...###...
...bbb...
...#.#...
..#...#..
.##...##.""",
    "ko": """
.........
.........
.........
.........
.........
.........
.........
.........
.........
HH.......
Hss####bs
Hss####b#
.........""",
}

BLUE = {"name": "BLAU", "body": (0, 90, 255), "hair": (40, 25, 10), "belt": (20, 20, 20)}
RED = {"name": "ROT", "body": (230, 0, 0), "hair": (255, 255, 255), "belt": (250, 200, 0)}


def draw_sprite(img, key, x0, y0, f, facing, flash=False):
    px = img.load()
    rows = S[key].strip("\n").split("\n")
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = {"#": f["body"], "H": f["hair"], "s": SKIN, "b": f["belt"]}[ch]
            if flash:
                c = (255, 255, 255)
            xx = x0 + (x if facing > 0 else len(row) - 1 - x)
            yy = y0 + y
            if ARENA[0] <= xx < ARENA[1] and 0 <= yy < H:
                px[xx, yy] = c


def draw_text(img, text, x0, w, color):
    if not text:
        return
    m = text_mask(text, H, max_width=w)
    img.paste(Image.new("RGB", m.size, color), (x0 + (w - m.width) // 2, 0), m)


class Scene:
    def __init__(self):
        self.a = {"x": 18, "pose": "idle", "hp": 100, "flash": 0, "y": 0, **BLUE}
        self.b = {"x": 101, "pose": "idle", "hp": 100, "flash": 0, "y": 0, **RED}
        self.balls = []
        self.msg2, self.msg3 = "", ""
        self.c2, self.c3 = (255, 255, 0), (255, 255, 255)
        self.blink = False
        self.frames = []
        self.t = 0

    def render(self):
        img = Image.new("RGB", (W, H))
        px = img.load()
        # health bars: 2 rows at the top of the arena
        for f, x0, sign in ((self.a, 2, 1), (self.b, 125, -1)):
            for i in range(56):
                x = x0 + i * sign
                c = (255, 220, 0) if i < f["hp"] * 56 // 100 else (90, 0, 0)
                px[x, 0] = c
                px[x, 1] = c
        # floor
        for x in range(ARENA[0], ARENA[1]):
            px[x, 15] = (40, 40, 60)
        draw_sprite(img, self.a["pose"], self.a["x"], 2 + self.a["y"], self.a, 1, self.a["flash"] > 0)
        draw_sprite(img, self.b["pose"], self.b["x"], 2 + self.b["y"], self.b, -1, self.b["flash"] > 0)
        for bx, col in self.balls:
            for dx, dy in ((0, 0), (1, 0), (2, 0), (1, -1), (1, 1), (3, 0)):
                if ARENA[0] <= bx + dx < ARENA[1]:
                    px[bx + dx, 8 + dy] = col if dx < 3 else (255, 255, 255)
        show = not self.blink or (self.t // 4) % 2 == 0
        if show:
            draw_text(img, self.msg2, 128, 64, self.c2)
            draw_text(img, self.msg3, 192, 96, self.c3)
        for f in (self.a, self.b):
            f["flash"] = max(0, f["flash"] - 1)
        self.frames.append(img)
        self.t += 1

    def hold(self, n):
        for _ in range(n):
            self.render()

    def bounce(self, n):
        for i in range(n):
            for f in (self.a, self.b):
                f["pose"] = "idle" if (self.t // 6) % 2 == 0 else "step"
            self.render()

    def walk(self, f, dx, n):
        for i in range(n):
            f["x"] += dx
            f["pose"] = "step" if (i // 3) % 2 else "idle"
            self.render()
        f["pose"] = "idle"

    def attack(self, att, dfn, move, dmg, push):
        att["pose"] = move
        self.hold(3)
        dfn["pose"], dfn["flash"] = "hit", 2
        dfn["hp"] = max(0, dfn["hp"] - dmg)
        for _ in range(push):
            dfn["x"] += 1 if dfn is self.b else -1
            self.render()
        att["pose"] = "idle"
        self.hold(3)
        dfn["pose"] = "idle"
        self.hold(2)

    def fireball(self, att, dfn, dmg):
        att["pose"] = "blast"
        self.hold(4)
        x = att["x"] + 9
        step = 3
        while x < dfn["x"]:
            self.balls = [(x, (0, 220, 255) if (self.t // 2) % 2 else (120, 120, 255))]
            self.render()
            x += step
        self.balls = []
        att["pose"] = "idle"
        dfn["pose"], dfn["flash"] = "hit", 3
        dfn["hp"] = max(0, dfn["hp"] - dmg)
        for _ in range(6):
            dfn["x"] += 1
            self.render()
        dfn["pose"] = "idle"
        self.hold(4)

    def jump_kick(self, att, dfn, dmg):
        arc = [-1, -2, -3, -3, -3, -2, -1, 0]
        att["pose"] = "kick"
        for dy in arc:
            att["y"] = dy
            att["x"] += 2
            self.render()
        dfn["pose"], dfn["flash"] = "hit", 3
        dfn["hp"] = max(0, dfn["hp"] - dmg)
        for _ in range(4):
            dfn["x"] -= 1
            self.render()
        att["pose"], dfn["pose"] = "idle", "idle"
        self.hold(3)


def build():
    s = Scene()
    s.msg2, s.msg3 = "VS", "ROUND 1"
    s.bounce(30)
    s.msg2, s.msg3, s.c2, s.blink = "", "FIGHT!", (255, 60, 0), True
    s.bounce(20)
    s.msg3, s.blink = "", False
    s.walk(s.a, 1, 22)
    s.walk(s.b, -1, 22)
    s.attack(s.a, s.b, "punch", 15, 3)
    s.walk(s.b, -1, 3)
    s.attack(s.b, s.a, "kick", 20, 5)
    s.walk(s.a, 1, 5)
    s.attack(s.a, s.b, "punch", 10, 2)
    s.attack(s.a, s.b, "kick", 15, 4)
    s.walk(s.a, -1, 12)
    s.fireball(s.a, s.b, 25)
    s.jump_kick(s.b, s.a, 25)
    s.walk(s.a, 1, 4)
    s.attack(s.a, s.b, "punch", 10, 2)
    s.bounce(6)
    s.attack(s.a, s.b, "kick", 25, 6)
    # knock-out
    s.b["pose"], s.b["hp"] = "ko", 0
    s.msg2, s.c2, s.blink = "K.O.", (255, 0, 0), True
    s.hold(24)
    s.blink = False
    s.msg3, s.c3 = "BLAU WINS", (0, 140, 255)
    for i in range(30):
        s.a["pose"] = "win" if (i // 6) % 2 == 0 else "idle"
        s.render()
    s.hold(10)
    return s.frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    ap.add_argument("--duration", type=int, default=6, help="10 ms units per frame")
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
    print(d.upload([build_spot(d.config, imgs, a.duration, "Fight")]).to_dict())


if __name__ == "__main__":
    main()
