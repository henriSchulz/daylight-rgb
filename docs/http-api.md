# HTTP API

`ko5g.server` serves the web UI (`web/`) at `/` and a JSON API under `/api/`.

```sh
export KO5G_HOST=<display-ip>
.venv/bin/python -m ko5g.server            # http://localhost:8080
.venv/bin/python -m ko5g.server --display <display-ip> --bind 127.0.0.1 --port 8080
```

| Option | Default | Meaning |
|---|---|---|
| `--display` | `$KO5G_HOST` | address of the display |
| `--bind` | `0.0.0.0` | listen address; use `127.0.0.1` to keep the server local |
| `--port` | 8080 | HTTP port |
| `--allow-remote-generate` | off | allow `/api/generate` from other computers |

The server has **no authentication**. Everyone who can reach it can change what the display shows.
Bind it to `127.0.0.1` or run it only in a trusted network.

All requests to the display are serialised (the controller handles one connection at a time).

## Conventions

- Request and response bodies are JSON. Every response has `ok: true|false`; errors carry `error`.
- Colours are hex strings (`"ff0000"`, `"#ff0000"`) or names (`red`, `green`, `blue`, `white`, `yellow`,
  `orange`, `cyan`, `magenta`, `black`).
- `duration` is in units of 10 ms per frame (100 = 1 s).
- **Every upload replaces the whole content of the display.**

## Endpoints

### `GET /api/status`

```json
{"ok": true,
 "config": {"width": 288, "height": 16, "board_type": 4, "shape": "rectangle", "fragment_size": [16, 8],
            "panels": [{"x": 0, "width": 128, "port": 1}, {"x": 128, "width": 64, "port": 2},
                       {"x": 192, "width": 96, "port": 3}],
            "wired_fragments": 36},
 "composition": {"spot_count": 1, "mode": "manual_spots", "frames_per_spot": [214]},
 "position": {"spot": 0, "frame": 146, "raw": "..."}}
```

### `POST /api/text`

Text rendered by the server (TrueType font) and uploaded.

| Field | Default | Meaning |
|---|---|---|
| `text` | – | the text |
| `color`, `background` | `ff0000`, `000000` | colours |
| `scroll` | `false` | right-to-left scrolling |
| `layout` | `panels` | `panels`: on every physical panel; `span`: once across the whole width |
| `step` | 1 | pixels per scroll frame |
| `duration` | 100 static, 3 scrolling | frame duration |

```sh
curl -X POST localhost:8080/api/text -d '{"text": "Hello", "color": "00ff00", "scroll": true}'
```

### `POST /api/upload`

Uploads finished frames, e.g. rendered in the browser.

```json
{"spots": [{"name": "Intro", "frames": [{"rgb": "<base64>", "duration": 5}, ...]}],
 "mode": "auto", "params": [1]}
```

- `rgb`: base64 of width x height x 3 bytes, RGB, row by row.
- `mode`: `manual_spots` (default), `auto`, `daily`, `weekly`, `manual_frames`.
- `params` per spot: auto = repeat count; daily = `[hour, minute]`; weekly = seven `[hour, minute]` or
  `null` (Monday first).
- The server compresses the frames and merges identical consecutive frames.

Response: `{"ok": true, "composition": {...}}`.

### `POST /api/mode`

`{"mode": "auto", "params": [1, 2], "disabled": [false, true]}` changes the playback mode of the stored
composition.

### `POST /api/switch`

`{"action": "next_spot" | "prev_spot" | "next_frame" | "prev_frame" | "goto", "spot": 0, "frame": 0}`.
`goto` counts from 0. The response contains the device reply (`aa aa` = OK, `cc cc` = does not exist).

### `POST /api/datetime`

Sets the display clock to the server's time.

### `POST /api/brightness` (experimental)

`{"level": 0..11}` (0 automatic, 1 = 100 % … 10 = 10 %, 11 off) for all hours. The device stores the value,
but on the tested display it had no visible effect (see [protocol.md §8](protocol.md#8-brightness-0x14)).

### Scene library

Scenes are animation descriptions in the [ko5g-scene format](scene-format.md), stored as
`scenes/<name>.scene.json`. Names may contain letters, digits, `_` and `-`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/scenes` | – | `{"scenes": [{"name", "title", "scenes", "frames"}]}` |
| GET | `/api/scenes/<name>` | – | `{"scene": {...}}` |
| POST | `/api/scenes/<name>` | scene document | `{"saved": "<name>"}` |
| DELETE | `/api/scenes/<name>` | – | `{"deleted": "<name>"}` |
| POST | `/api/scenes/<name>/play` | – | renders and uploads; `{"composition": {...}}` |
| POST | `/api/scene/play` | scene document | renders and uploads without saving |

### `POST /api/generate`

Creates a scene document from a text description with the Claude CLI. Details:
[ai-generation.md](ai-generation.md).

```json
{"prompt": "a sailboat at sunset", "scene": null, "model": null}
```

- Only allowed from the computer the server runs on, unless `--allow-remote-generate` is set.
- Takes 20–90 s; one generation at a time (`409` while busy).
- Returns `{"scene", "attempts", "cost_usd", "seconds", "frames"}`. It does **not** send anything to
  the display; use `/api/scene/play` for that.

## Error codes

| HTTP | Meaning |
|---|---|
| 400 | invalid request (missing field, bad JSON, bad name) |
| 403 | `/api/generate` from a remote computer |
| 404 | unknown endpoint or scene |
| 409 | a generation is already running |
| 422 | the generated scene could not be validated |
| 500 | device or protocol error (message in `error`) |
