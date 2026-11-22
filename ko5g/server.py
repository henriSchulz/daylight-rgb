"""HTTP API for the Ko5G display.  Run:  .venv/bin/python -m ko5g.server --display <display-ip> [--port 8080]

Serves web/ at /  and JSON endpoints under /api/ (see README.md).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from . import Display, MODES
from . import frames as fr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SCENES = os.path.join(ROOT, "scenes")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _scene_path(name: str) -> str:
    if not NAME_RE.match(name):
        raise ValueError("invalid name (allowed: letters, digits, _ and -)")
    return os.path.join(SCENES, f"{name}.scene.json")


def scenes_api(method: str, parts: list, body):
    """/api/scenes[/<name>[/play]]"""
    from .scene import Renderer, SceneError
    if len(parts) == 0 and method == "GET":
        out = []
        for fn in sorted(os.listdir(SCENES)) if os.path.isdir(SCENES) else []:
            if fn.endswith(".scene.json"):
                try:
                    with open(os.path.join(SCENES, fn), encoding="utf-8") as f:
                        doc = json.load(f)
                    out.append({"name": fn[:-11], "title": doc.get("title", fn[:-11]),
                                "scenes": len(doc.get("scenes", [])),
                                "frames": sum(int(s.get("frames", 0)) for s in doc.get("scenes", []))})
                except (OSError, ValueError):
                    out.append({"name": fn[:-11], "error": "unreadable"})
        return {"scenes": out}
    name = parts[0] if parts else ""
    path = _scene_path(name)
    if len(parts) == 1 and method == "GET":
        with open(path, encoding="utf-8") as f:
            return {"scene": json.load(f)}
    if len(parts) == 1 and method == "POST":
        Renderer(body)  # validates format/version
        for sc in body.get("scenes", []):
            if int(sc.get("frames", 0)) <= 0 or "layers" not in sc:
                raise SceneError("each scene needs frames > 0 and layers")
        os.makedirs(SCENES, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        return {"saved": name}
    if len(parts) == 1 and method == "DELETE":
        os.remove(path)
        return {"deleted": name}
    if len(parts) == 2 and parts[1] == "play" and method == "POST":
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return {"composition": display.play_scene(doc, log=lambda *_: None).to_dict()}
    raise KeyError("/api/scenes/" + "/".join(parts))
LOCK = threading.Lock()          # the controller handles one connection at a time
display: Display | None = None
ALLOW_REMOTE_GENERATE = False    # /api/generate runs the Claude CLI at the user's expense: localhost only
MODEL_RE = re.compile(r"^[a-z][a-z0-9.\-\[\]]{0,63}$")


def _spot_from_rgb(spot: dict) -> dict:
    cfg = display.config
    images, durations = [], []
    for i, f in enumerate(spot.get("frames", [])):
        raw = base64.b64decode(f["rgb"])
        if len(raw) != cfg.width * cfg.height * 3:
            raise ValueError(f"frame {i}: expected {cfg.width * cfg.height * 3} bytes, got {len(raw)}")
        images.append(Image.frombytes("RGB", (cfg.width, cfg.height), raw))
        durations.append(int(f.get("duration", 100)))
    if not images:
        raise ValueError("spot without frames")
    return fr.build_spot(cfg, images, durations, spot.get("name", "Spot"))


def api(path: str, body: dict, method: str = "POST"):
    d = display
    if path == "/api/scenes" or path.startswith("/api/scenes/"):
        return scenes_api(method, [p for p in path[len("/api/scenes"):].split("/") if p], body)
    if path == "/api/scene/play" and method == "POST":
        return {"composition": d.play_scene(body, log=lambda *_: None).to_dict()}
    if path == "/api/status":
        return d.info()
    if path == "/api/upload":
        spots = [_spot_from_rgb(s) for s in body["spots"]]
        comp = d.upload(spots, body.get("mode", "manual_spots"), body.get("params"), log=lambda *_: None)
        return {"composition": comp.to_dict()}
    if path == "/api/text":
        spot = d.make_text_spot(body["text"], color=body.get("color", "ff0000"),
                                background=body.get("background", "000000"), scroll=bool(body.get("scroll")),
                                layout=body.get("layout", "panels"), step=int(body.get("step", 1)),
                                duration=body.get("duration"))
        return {"composition": d.upload([spot], log=lambda *_: None).to_dict()}
    if path == "/api/datetime":
        d.set_time()
        return {}
    if path == "/api/brightness":
        level = int(body["level"])
        if not 0 <= level <= 11:
            raise ValueError("level 0..11")
        block = bytearray(d.conn.read_config().brightness)
        block[0:168] = bytes([level]) * 168
        d.conn.write_brightness_block(bytes(block))
        return {"experimental": True}
    if path == "/api/mode":
        d.set_mode(body["mode"], body.get("params"), body.get("disabled"))
        return {"composition": d.conn.read_composition().to_dict()}
    if path == "/api/switch":
        action = body["action"]
        fn = {"next_spot": d.next_spot, "prev_spot": d.prev_spot, "next_frame": d.next_frame,
              "prev_frame": d.prev_frame}.get(action)
        r = fn() if fn else d.goto(int(body.get("spot", 1)), int(body.get("frame", 1)))
        return {"reply": r[:8].hex(" ")}
    raise KeyError(path)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def _json(self, code: int, obj: dict):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_api(self, body, method="POST"):
        try:
            with LOCK:
                self._json(200, {"ok": True, **api(self.path.split("?")[0], body, method)})
        except FileNotFoundError:
            self._json(404, {"ok": False, "error": "not found"})
        except KeyError as e:
            self._json(404 if str(e).strip("'").startswith("/api") else 400, {"ok": False, "error": f"missing {e}"})
        except Exception as e:  # noqa: BLE001 - report every device/protocol error to the client
            traceback.print_exc()
            self._json(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._handle_api({}, "GET")
        return super().do_GET()

    def do_DELETE(self):
        if not self.path.startswith("/api/"):
            return self._json(404, {"ok": False, "error": "not found"})
        return self._handle_api({}, "DELETE")

    def do_POST(self):
        if not self.path.startswith("/api/"):
            return self._json(404, {"ok": False, "error": "not found"})
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            return self._json(400, {"ok": False, "error": f"bad JSON: {e}"})
        if self.path.split("?")[0] == "/api/generate":
            return self._generate(body)
        return self._handle_api(body, "POST")

    def _generate(self, body):
        """POST /api/generate {prompt, scene?, model?} -> {scene, attempts, cost_usd, seconds, frames}.
        Runs outside LOCK (a CLI call takes up to minutes) and never talks to the display."""
        from .ai import GenerateError, generate
        if not ALLOW_REMOTE_GENERATE and self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return self._json(403, {"ok": False, "error": "AI generation is only allowed from this computer "
                                                          "(start the server with --allow-remote-generate)"})
        model = body.get("model")
        if model is not None and not (isinstance(model, str) and MODEL_RE.match(model)):
            return self._json(400, {"ok": False, "error": "invalid model name"})
        current = body.get("scene")
        if current is not None and not isinstance(current, dict):
            return self._json(400, {"ok": False, "error": "scene must be an object"})
        try:
            with LOCK:  # short: the config may be read from the device on first access
                cfg = display.config
                panels, width, height = cfg.panels(), cfg.width, cfg.height
            res = generate(str(body.get("prompt", "")), current, panels, width, height, model=model)
            self._json(200, {"ok": True, **res})
        except GenerateError as e:
            self._json(409 if str(e).startswith("busy") else 422, {"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"ok": False, "error": str(e)})


def main():
    global display
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", default=os.environ.get("KO5G_HOST"),
                    help="display IP or host name (default: $KO5G_HOST)")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--allow-remote-generate", action="store_true",
                    help="allow /api/generate (Claude CLI, costs money) from other computers, not only localhost")
    a = ap.parse_args()
    global ALLOW_REMOTE_GENERATE
    ALLOW_REMOTE_GENERATE = a.allow_remote_generate
    if not a.display:
        ap.error("no display address: use --display <ip> or set KO5G_HOST")
    display = Display(a.display)
    os.makedirs(WEB, exist_ok=True)
    print(f"ko5g API on http://{a.bind}:{a.port}  ->  display {a.display}")
    ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
