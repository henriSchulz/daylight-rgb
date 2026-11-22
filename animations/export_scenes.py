"""Converts the Python animations (walkers, fight, race) into ko5g-scene files in scenes/.

    .venv/bin/python animations/export_scenes.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import fight  # noqa: E402
import race  # noqa: E402
import walkers  # noqa: E402

from ko5g.scene import text_bitmap, value  # noqa: E402

OUT = os.path.join(ROOT, "scenes")


def hexc(c):
    return "#%02x%02x%02x" % tuple(c)


def rows(s):
    return s.strip("\n").split("\n")


# -- keyframe compression ---------------------------------------------------------------
def keys_linear(vals):
    """Minimal linear keyframes that reproduce the integer sequence exactly (spec rounding)."""
    n = len(vals)
    if all(v == vals[0] for v in vals):
        return vals[0]
    keys = [[0, vals[0]]]
    s = 0
    while s < n - 1:
        e = s + 1
        while e + 1 < n:
            cand = {"keys": [[s, vals[s]], [e + 1, vals[e + 1]]]}
            if all(value(cand, t) == vals[t] for t in range(s, e + 2)):
                e += 1
            else:
                break
        keys.append([e, vals[e]])
        s = e
    return {"keys": keys}


def keys_step(vals):
    if all(v == vals[0] for v in vals):
        return vals[0]
    keys = [[0, vals[0]]]
    for t in range(1, len(vals)):
        if vals[t] != vals[t - 1]:
            keys.append([t, vals[t]])
    return {"keys": keys, "ease": "step"}


def check_keys(spec, vals):
    for t, v in enumerate(vals):
        assert value(spec, t) == v, (t, v, value(spec, t))
    return spec


# -- walkers ------------------------------------------------------------------------------
def scene_walkers():
    sprite = {"frames": [rows(s) for s in walkers.WALK] + [rows(walkers.JUMP)],
              "colors": {"s": hexc(walkers.SKIN)}}
    layers = []
    n = 288
    for i, (sx, body, hair, d, jumper) in enumerate(walkers.PEOPLE):
        base = {"type": "sprite", "sprite": "person", "wrap": True,
                "colors": {"#": hexc(body), "H": hexc(hair)},
                "x": {"keys": [[0, sx], [n, sx + n]]}}
        walk = {**base, "y": 3, "cycle": {"seq": [0, 1, 2, 3], "every": 3, "offset": 3 * i}}
        if not jumper:
            layers.append(walk)
            continue
        # jump every 36 frames, during frames 27..35 of each period
        walk["visible"] = {"keys": [[0, 1], [27, 0]], "ease": "step", "repeat": 36}
        curve = [0, -1, -2, -3, -3, -3, -2, -1, 0]
        jump = {**base, "frame": 4, "visible": {"keys": [[0, 0], [27, 1]], "ease": "step", "repeat": 36},
                "y": {"keys": [[27 + k, 3 + c] for k, c in enumerate(curve)], "ease": "step", "repeat": 36}}
        layers += [walk, jump]
    return {"format": "ko5g-scene", "version": 1, "title": "Pixel people", "fps": 20,
            "sprites": {"person": sprite},
            "scenes": [{"name": "Walkers", "frames": n, "layers": layers}]}


# -- fight ----------------------------------------------------------------------------------
class RecordingScene(fight.Scene):
    def __init__(self):
        super().__init__()
        self.rec = []

    def render(self):
        show = not self.blink or (self.t // 4) % 2 == 0
        self.rec.append({
            "ax": self.a["x"], "ay": self.a["y"], "ap": self.a["pose"], "af": int(self.a["flash"] > 0), "ahp": self.a["hp"],
            "bx": self.b["x"], "by": self.b["y"], "bp": self.b["pose"], "bf": int(self.b["flash"] > 0), "bhp": self.b["hp"],
            "ball": self.balls[0] if self.balls else None,
            "m2": (self.msg2, hexc(self.c2)) if (self.msg2 and show) else None,
            "m3": (self.msg3, hexc(self.c3)) if (self.msg3 and show) else None,
        })
        for f in (self.a, self.b):
            f["flash"] = max(0, f["flash"] - 1)
        self.frames.append(None)
        self.t += 1


def text_layers(rec, key, panel):
    """One text layer per distinct (text, colour); visibility as step keys."""
    out = []
    variants = sorted({r[key] for r in rec if r[key]}, key=str)
    for txt, col in variants:
        vis = [1 if r[key] == (txt, col) else 0 for r in rec]
        out.append({"type": "text", "text": txt, "color": col, "panel": panel, "scale": fit_scale(txt, panel),
                    "visible": check_keys(keys_step(vis), vis)})
    return out


PANEL_W = {1: 128, 2: 64, 3: 96}


def fit_scale(txt, panel):
    return 2 if text_bitmap(txt, 2)[0] <= PANEL_W[panel] else 1


def record_fight():
    orig = fight.Scene
    holder = {}

    class Rec(RecordingScene):
        def __init__(self):
            super().__init__()
            holder["s"] = self

    fight.Scene = Rec
    try:
        fight.build()
    finally:
        fight.Scene = orig
    return holder["s"].rec


def scene_fight_doc():
    rec = record_fight()
    n = len(rec)
    poses = list(fight.S.keys())
    sprite = {"frames": [rows(fight.S[p]) for p in poses], "colors": {"s": hexc(fight.SKIN)}}
    arena = [0, 0, 128, 16]
    layers = [
        {"type": "rect", "x": 0, "y": 15, "w": 128, "h": 1, "color": "#28283c"},
        {"type": "bar", "x": 2, "y": 0, "w": 56, "h": 2, "color": "#ffdc00", "back": "#5a0000", "dir": "ltr",
         "value": check_keys(keys_step([r["ahp"] for r in rec]), [r["ahp"] for r in rec])},
        {"type": "bar", "x": 70, "y": 0, "w": 56, "h": 2, "color": "#ffdc00", "back": "#5a0000", "dir": "rtl",
         "value": check_keys(keys_step([r["bhp"] for r in rec]), [r["bhp"] for r in rec])},
    ]
    for who, f, flip in (("a", fight.BLUE, 0), ("b", fight.RED, 1)):
        xs = [r[who + "x"] for r in rec]
        ys = [2 + r[who + "y"] for r in rec]
        ps = [poses.index(r[who + "p"]) for r in rec]
        fl = [r[who + "f"] for r in rec]
        layers.append({"type": "sprite", "sprite": "fighter", "clip": arena, "flip": flip,
                       "colors": {"#": hexc(f["body"]), "H": hexc(f["hair"]), "b": hexc(f["belt"])},
                       "x": check_keys(keys_linear(xs), xs), "y": check_keys(keys_linear(ys), ys),
                       "frame": check_keys(keys_step(ps), ps), "flash": check_keys(keys_step(fl), fl)})
    # energy ball: sprite with two colour frames
    bx = [r["ball"][0] if r["ball"] else -100 for r in rec]
    bc = [(0 if r["ball"][1] == (0, 220, 255) else 1) if r["ball"] else 0 for r in rec]
    bv = [1 if r["ball"] else 0 for r in rec]
    layers.append({"type": "sprite", "sprite": "ball", "clip": arena, "y": 7,
                   "x": check_keys(keys_linear(bx), bx), "frame": check_keys(keys_step(bc), bc),
                   "visible": check_keys(keys_step(bv), bv)})
    layers += text_layers(rec, "m2", 2) + text_layers(rec, "m3", 3)
    ball = {"frames": [[".a..", "aaaw", ".a.."], [".b..", "bbbw", ".b.."]],
            "colors": {"a": "#00dcff", "b": "#7878ff", "w": "#ffffff"}}
    return {"format": "ko5g-scene", "version": 1, "title": "Fight", "fps": 17,
            "sprites": {"fighter": sprite, "ball": ball},
            "scenes": [{"name": "Fight", "frames": n, "layers": layers}]}


# -- race -----------------------------------------------------------------------------------
def scene_race():
    car_rows = rows(race.CAR)
    def car_frame(moving_phase):
        out = []
        for row in car_rows:
            r = ""
            for x, ch in enumerate(row):
                if ch == "O":
                    r += "L" if moving_phase is not None and (x + moving_phase) % 2 else "O"
                else:
                    r += ch
            out.append(r)
        return out
    car = {"frames": [car_frame(None), car_frame(0), car_frame(1)],
           "colors": {"w": "#96dcff", "h": "#ffffb4", "O": "#464646", "L": "#c8c8c8"}}
    countdown = [("3", "#ff0000", 14), ("2", "#ff0000", 14), ("1", "#ffa000", 14), ("GO!", "#00ff00", 10)]
    t_start = sum(n for _, _, n in countdown)
    # race positions (same function as race.py, truncated like the original)
    race_len = 0
    while True:
        done = all(race.smooth(k, race_len) >= race.W for _, _, _, k in race.CARS)
        race_len += 1
        if done or race_len > 200:
            break
    t_win = t_start + race_len
    total = t_win + 50
    layers = [
        {"type": "pattern", "x": 0, "y": 15, "w": 288, "h": 1, "rows": ["###..."], "colors": {"#": "#3c3c3c"}},
        {"type": "pattern", "x": race.FINISH, "y": 0, "w": 2, "h": 15, "rows": ["#.", "#.", ".#", ".#"],
         "colors": {"#": "#ffffff"}, "to": t_win},
        {"type": "pattern", "x": race.FINISH, "y": 0, "w": 2, "h": 15, "rows": [".#", ".#", "#.", "#."],
         "colors": {"#": "#1e1e1e"}, "to": t_win},
        {"type": "rect", "x": 15, "y": 0, "w": 1, "h": 15, "color": "#787878", "to": t_win},
    ]
    for name, colour, lane, keys in race.CARS:
        xs = [keys[0][1]] * t_start + [int(race.smooth(keys, t)) for t in range(race_len)] + [-100] * 50
        frames_ = [0] * t_start + [1 + (t % 2) for t in range(race_len)] + [0] * 50
        puff_vis = [1 if (t % 4 < 2) else 0 for _, _, n in countdown for t in range(n)][:t_start] \
            + [1 if t % 3 == 0 else 0 for t in range(race_len)] + [0] * 50
        puff_dx = [-1] * t_start + [-2] * race_len + [-2] * 50
        puff_x = [x + d for x, d in zip(xs, puff_dx)]
        layers.append({"type": "sprite", "sprite": "car", "y": lane, "to": t_win, "colors": {"#": hexc(colour)},
                       "x": check_keys(keys_linear(xs), xs), "frame": check_keys(keys_step(frames_), frames_)})
        layers.append({"type": "pixels", "y": lane + 3, "to": t_win, "points": [[0, 0, "#787878"]],
                       "x": check_keys(keys_linear(puff_x), puff_x),
                       "visible": check_keys(keys_step(puff_vis), puff_vis)})
    # countdown: black box over panels 2+3 and the numbers on panel 3
    layers.append({"type": "rect", "x": 128, "y": 0, "w": 160, "h": 16, "color": "#000000", "to": t_start})
    t = 0
    for label, col, n in countdown:
        layers.append({"type": "text", "text": label, "color": col, "panel": 3, "from": t, "to": t + n})
        t += n
    # winner: first car whose front crosses the finish
    winner = None
    for tt in range(race_len):
        for name, colour, lane, keys in race.CARS:
            if winner is None and race.smooth(keys, tt) + 11 >= race.FINISH:
                winner = (name, colour)
    wname, wcol = winner
    layers += [
        {"type": "rect", "x": 0, "y": 0, "w": 288, "h": 16, "color": "#000000", "from": t_win},
        {"type": "text", "text": "SIEG!", "color": "#ffdc00", "panel": 1, "from": t_win, "blink": [5, 5]},
        {"type": "text", "text": "SIEG!", "color": "#ffffff", "panel": 1, "from": t_win + 5, "blink": [5, 5]},
        {"type": "sprite", "sprite": "car", "x": 154, "y": 6, "from": t_win, "colors": {"#": hexc(wcol)},
         "cycle": {"seq": [1, 2], "every": 1}},
        {"type": "text", "text": wname, "color": hexc(wcol), "panel": 3, "from": t_win},
    ]
    for k, (sx, sy) in enumerate([(134, 1), (147, 4), (170, 0), (183, 3), (140, 13), (178, 12)]):
        layers.append({"type": "pixels", "x": sx, "y": sy, "points": [[0, 0, "#ffff78"]], "from": t_win + k % 3,
                       "blink": [2, 4]})
    return {"format": "ko5g-scene", "version": 1, "title": "Car race", "fps": 20,
            "sprites": {"car": car},
            "scenes": [{"name": "Race", "frames": total, "layers": layers}]}


def main():
    os.makedirs(OUT, exist_ok=True)
    docs = {"walkers": scene_walkers(), "fight": scene_fight_doc(), "race": scene_race()}
    for name, doc in docs.items():
        path = os.path.join(OUT, f"{name}.scene.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{path}: {os.path.getsize(path)} B, {sum(s['frames'] for s in doc['scenes'])} frames")
    # playlist with all three
    pl = {"format": "ko5g-scene", "version": 1, "title": "Playlist", "fps": 20, "mode": "auto",
          "sprites": {}, "scenes": []}
    for name, doc in docs.items():
        for sc in doc["scenes"]:
            pl["sprites"].update(doc["sprites"])
            pl["scenes"].append({**sc, "fps": doc.get("fps", 20)})
    with open(os.path.join(OUT, "playlist.scene.json"), "w", encoding="utf-8") as f:
        json.dump(pl, f, ensure_ascii=False, separators=(",", ":"))
    print("playlist.scene.json", os.path.getsize(os.path.join(OUT, "playlist.scene.json")), "B")


if __name__ == "__main__":
    main()
