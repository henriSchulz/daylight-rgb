"""Generate ko5g-scene animations from a text prompt with the Claude CLI (`claude -p`).

The model gets the scene format spec and the display facts, writes one scene file,
and the result is checked with the reference renderer (scene.Renderer). Errors go back
to the model for up to MAX_REPAIRS repair rounds. Nothing here talks to the display.

    .venv/bin/python -m ko5g.ai "a red car overtakes a blue one"   # prints the scene JSON
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

from .scene import Renderer, SceneError, _load_font

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "docs", "scene-format.md")
CLI_TIMEOUT = 240          # seconds per CLI call
MAX_REPAIRS = 2
MAX_FRAMES_PER_SCENE = 1200   # server hard limit is 6000; generated scenes stay well below
MAX_FRAMES_TOTAL = 10000
MAX_SCENES = 20
MAX_PROMPT = 2000
_busy = threading.Lock()   # one generation at a time (each call costs money)


class GenerateError(RuntimeError):
    pass


def _system_prompt(width: int, height: int, panels: list) -> str:
    with open(SPEC, encoding="utf-8") as f:
        spec = f.read()
    glyphs = "".join(sorted(k for k in _load_font() if len(k) == 1)) + " "
    pan = ", ".join(f"panel {i + 1} = x {p['x']}–{p['x'] + p['width'] - 1}" for i, p in enumerate(panels))
    return f"""You design animations for a physical RGB LED sign and write them as ko5g-scene files.

Display: {width} x {height} LEDs, one continuous strip (the panels sit flush, no gaps): {pan}.
Each LED is a bright dot; 8 bit per colour channel. Frame duration on the device = round(100/fps) x 10 ms.

Output rules:
- Reply with exactly ONE JSON object: a complete ko5g-scene version 1 document. No prose, no Markdown, no code fences.
- Every colour must be "#rrggbb" or a name defined in "colors". Every sprite character needs a colour.
- Text layers can only use these characters (others render as "?"): {glyphs}
  Glyphs are about 5 columns wide plus 1 gap at scale 1 (8 px tall); scale 2 doubles that (16 px tall,
  roughly 12 px per character, so at most about 22 characters fit across the full width at scale 2).
- Keep each scene at most {MAX_FRAMES_PER_SCENE} frames; fps between 8 and 30. Prefer 10–25 s total.
- Sprites: at most {height} rows; design them as clear pixel art with 2–4 colours.
- Write "title" and scene "name" in the language of the request.

Design guidance for LEDs:
- Black background unless asked otherwise. Use saturated, bright colours; values below about 40 per
  channel are nearly invisible, mid-greys look muddy.
- Text must stay readable: either static, or moving horizontally at about 20–60 px per second
  (x keyframes, ease "linear"). Do not move text vertically and horizontally at once.
- Make loops seamless: the last frame should lead back into the first (use "repeat" on keyframes and
  "cycle" for sprite animation).
- Use the whole strip: 288 x 16 is very wide and very flat. Layer depth: background patterns first,
  figures in the middle, text on top.
- If the request is vague, make a confident, playful choice.

Originality: use only original figures and designs. Never reproduce characters, logos, mascots or levels
from existing games, films, comics or brands, even if the request names them; in that case build an
original figure in the same spirit (e.g. "a plumber-like hero" becomes your own little worker figure).
Text is limited to the glyphs listed above.

If the user message contains a CURRENT DOCUMENT, change it as requested and return the whole updated
document; keep everything the request does not mention.

The format specification follows.

{spec}
"""


def _extract_json(text: str) -> dict:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b < a:
            raise GenerateError("the model did not return JSON")
        t = t[a:b + 1]
    try:
        doc = json.loads(t)
    except json.JSONDecodeError as e:
        raise SceneError(f"invalid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise SceneError("top level must be a JSON object")
    return doc


def validate(doc: dict, width: int, height: int, panels: list) -> dict:
    """Render every frame with the reference renderer. Returns stats; raises SceneError."""
    r = Renderer(doc, width, height, panels)
    scenes = doc.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise SceneError("the document has no scenes")
    if len(scenes) > MAX_SCENES:
        raise SceneError(f"at most {MAX_SCENES} scenes, has {len(scenes)}")
    counts = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict) or not isinstance(sc.get("layers"), list):
            raise SceneError(f"scene {i + 1}: needs a layers list")
        n = int(sc.get("frames", 0))
        if not 0 < n <= MAX_FRAMES_PER_SCENE:
            raise SceneError(f"scene {i + 1}: frames must be 1..{MAX_FRAMES_PER_SCENE}, is {n}")
        counts.append(n)
    if sum(counts) > MAX_FRAMES_TOTAL:
        raise SceneError(f"at most {MAX_FRAMES_TOTAL} frames in total, has {sum(counts)}")
    frames, lit = 0, False
    for i, (sc, n) in enumerate(zip(scenes, counts)):
        fps = r.fps(sc)
        if not 1 <= fps <= 50:
            raise SceneError(f"scene {i + 1}: fps must be 1..50, is {fps}")
        bg = r.color(sc.get("background", "#000000"))
        for t in range(n):
            img = r.render(sc, t)
            if not lit and (img.getcolors(1) is None or img.getpixel((0, 0)) != bg):
                lit = True   # more than one colour, or a single colour that is not the background
            frames += 1
    if not lit:
        raise SceneError("nothing is visible: every frame shows only the background")
    return {"scenes": len(scenes), "frames": frames}


def _run_cli(system: str, prompt: str, model: str | None) -> tuple[str, float]:
    exe = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    if not os.path.exists(exe):
        raise GenerateError("Claude CLI not found (claude is not on PATH)")
    cmd = [exe, "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
           "--no-session-persistence", "--system-prompt", system]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    with tempfile.TemporaryDirectory(prefix="ko5g-ai-") as cwd:  # no project files in reach
        try:
            p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=CLI_TIMEOUT)
        except subprocess.TimeoutExpired as e:
            raise GenerateError(f"Claude CLI did not answer within {CLI_TIMEOUT} s") from e
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        msg = (p.stderr or p.stdout).strip().splitlines()
        raise GenerateError(f"Claude CLI failed: {msg[-1] if msg else f'exit code {p.returncode}'}")
    if out.get("is_error"):
        raise GenerateError(f"Claude CLI: {out.get('result') or out.get('subtype') or 'error'}")
    return out.get("result", ""), float(out.get("total_cost_usd") or 0)


def generate(prompt: str, current: dict | None = None, panels: list | None = None,
             width: int = 288, height: int = 16, model: str | None = None, log=lambda *_: None) -> dict:
    """Returns {scene, attempts, cost_usd, seconds, frames}."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise GenerateError("empty prompt")
    if len(prompt) > MAX_PROMPT:
        raise GenerateError(f"prompt too long (max {MAX_PROMPT} characters)")
    panels = [{"x": int(p["x"]), "width": int(p["width"])} for p in (panels or [{"x": 0, "width": width}])]
    if not _busy.acquire(blocking=False):
        raise GenerateError("busy: a generation is already running")
    try:
        system = _system_prompt(width, height, panels)
        user = prompt if current is None else (
            f"{prompt}\n\nCURRENT DOCUMENT:\n{json.dumps(current, ensure_ascii=False)}")
        t0, cost, last_text = time.time(), 0.0, ""
        for attempt in range(1, MAX_REPAIRS + 2):
            text, c = _run_cli(system, user, model)
            cost += c
            last_text = text
            try:
                doc = _extract_json(text)
                stats = validate(doc, width, height, panels)
            except SceneError as e:
                log(f"attempt {attempt}: {e}")
                if attempt > MAX_REPAIRS:
                    raise GenerateError(f"no valid animation after {attempt} attempts: {e}") from e
                user = (f"Original request: {prompt}\n\nYour previous document:\n{last_text}\n\n"
                        f"It fails with this error: {e}\n"
                        "Fix it and return the complete corrected document.")
                continue
            return {"scene": doc, "attempts": attempt, "cost_usd": round(cost, 4),
                    "seconds": round(time.time() - t0, 1), "frames": stats["frames"]}
        raise GenerateError("unreachable")
    finally:
        _busy.release()


if __name__ == "__main__":
    import sys
    res = generate(" ".join(sys.argv[1:]) or "Ein Feuerwerk über einer Stadt", log=lambda m: print(m, file=sys.stderr),
                   panels=[{"x": 0, "width": 128}, {"x": 128, "width": 64}, {"x": 192, "width": 96}])
    print(f"{res['attempts']} attempt(s), {res['seconds']} s, ${res['cost_usd']}, {res['frames']} frames", file=sys.stderr)
    print(json.dumps(res["scene"], ensure_ascii=False))
