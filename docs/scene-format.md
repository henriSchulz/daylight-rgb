# ko5g-scene – a description format for animations (version 1)

A `.scene.json` file describes **what happens** on the display. An interpreter
(`ko5g/scene.py` in Python and the web page in JavaScript) computes the frames from it.
Both interpreters must produce **exactly the same pixels**; that is why time, rounding and
the font are fixed below.

Files only describe drawing; they never contain executable code.

## File

```json
{
  "format": "ko5g-scene",
  "version": 1,
  "title": "Car race",
  "fps": 20,
  "colors":  { "red": "#e60000" },
  "sprites": { "car": { "frames": [["..##..", "######"]], "colors": { "#": "red" } } },
  "mode": "auto",
  "scenes": [ { "name": "Race", "frames": 256, "layers": [ ... ] } ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `format`, `version` | yes | always `"ko5g-scene"`, `1` |
| `title` | no | display name |
| `fps` | no | frames per second, default 20. Frame duration on the device = `round(100 / fps)` units of 10 ms |
| `colors` | no | palette: name → `"#rrggbb"` |
| `sprites` | no | pixel figures (see below) |
| `mode` | no | `"manual_spots"` (default with 1 scene) or `"auto"` (default with several scenes: they play in turn) |
| `scenes` | yes | list of scenes; each scene becomes one spot on the display |

## Scene

| Field | Required | Meaning |
|---|---|---|
| `name` | no | name (max. 30 characters) |
| `frames` | yes | length in frames |
| `fps` | no | overrides the file's `fps` |
| `background` | no | colour, default `"#000000"` |
| `repeat` | no | how often the scene runs in a row in `auto` mode, default 1 |
| `layers` | yes | drawing layers, drawn in the order of the list (later = in front) |

The display is `width` x `height` (here 288 x 16). Origin at top left, x to the right, y down.
Panels (`panel` 1, 2, 3) come from the device configuration: panel 1 = x 0–127, panel 2 = x 128–191,
panel 3 = x 192–287. If the configuration is unknown, the whole width counts as panel 1.

## Colours

`"#rrggbb"` or a name from `colors`. Unknown names are an error.

## Animated values

Every numeric field marked **(V)** may be:

- a number: `5`
- keyframes: `{"keys": [[0, 2], [20, 30], [60, 95]], "ease": "smooth", "repeat": 0}`

`keys` = list of `[frame, value]`, sorted by frame. Evaluation at frame `t`:

1. If `repeat` > 0: `t = t mod repeat`.
2. `t` ≤ first key → first value; `t` ≥ last key → last value.
3. Between key `(ta, va)` and `(tb, vb)`: `u = (t − ta) / (tb − ta)`
   - `"linear"` (default): `v = va + (vb − va) · u`
   - `"smooth"`: `u' = (1 − cos(π·u)) / 2`, `v = va + (vb − va) · u'`
   - `"step"`: `v = va`
4. **Rounding:** the result is always `floor(v + 0.5)` (no banker's rounding).

## Common layer fields

| Field | Meaning |
|---|---|
| `type` | `sprite`, `text`, `rect`, `bar`, `pattern`, `pixels` |
| `from`, `to` | visible only for `from ≤ t < to` (default: whole scene) |
| `blink` | `[on, off]`: visible while `(t − from) mod (on + off) < on` |
| `visible` (V) | 0 = not drawn |
| `clip` | `[x0, y0, x1, y1]`: draw only inside (x1/y1 exclusive). Default: whole display |

Pixels outside the display are dropped. With `"wrap": true` (sprite, text, pixels), x is taken modulo the
display width instead.

## Layer types

### `sprite`
```json
{"type": "sprite", "sprite": "car", "x": 2, "y": 0, "frame": 0, "flip": 0, "colors": {"#": "red"}, "flash": 0}
```
- `x`, `y` (V): top-left corner.
- `frame` (V): index into `frames` of the sprite (modulo the number of frames).
  Alternative `"cycle": {"seq": [0, 1, 2, 3], "every": 3, "offset": 0}` →
  `frame = seq[floor((t + offset) / every) mod len(seq)]`.
- `flip` (V): 1 = mirror horizontally (the sprite then faces left).
- `colors`: overrides the sprite's colour assignment (character → colour).
- `flash` (V): 1 = draw every visible pixel in `flash_color` (default `#ffffff`), e.g. for hits.

Sprite definition: `{"frames": [[row, row, ...], ...], "colors": {"char": colour}}`.
All frames of a sprite have the same width and height. `.` and space are transparent.
Characters without a colour assignment are an error.

### `text`
```json
{"type": "text", "text": "GO!", "color": "#00ff00", "panel": 3, "align": "center", "scale": 2, "x": 0, "y": 0}
```
- Font: the pixel font from `web/font5x8.js` (proportional, 8 rows, 1 column of space between glyphs,
  space = 3 columns wide). `scale` 1 = 8 px tall, 2 = 16 px tall (default 2).
- Area: `"panel": n` or `"region": [x0, width]`; default: the whole width.
- `align`: `center` (default), `left`, `right`. Position:
  `left = x0`, `right = x0 + width − text width`, `center = x0 + floor((width − text width) / 2)`;
  then `+ x` (V). Vertically: `floor((height − text height) / 2) + y` (V).
- Text wider than the area is not shrunk (use `clip` to cut it off).

### `rect`
```json
{"type": "rect", "x": 0, "y": 15, "w": 128, "h": 1, "color": "#28283c"}
```
`x`, `y`, `w`, `h` (V).

### `bar`
```json
{"type": "bar", "x": 2, "y": 0, "w": 56, "h": 2, "value": 100, "color": "#ffdc00", "back": "#5a0000", "dir": "ltr"}
```
`value` (V) 0–100. Filled length = `floor(w · value / 100)`, starting from the left (`ltr`) or
from the right (`rtl`); the rest in `back` (optional, otherwise transparent).

### `pattern`
```json
{"type": "pattern", "x": 0, "y": 15, "w": 288, "h": 1, "rows": ["###..."], "colors": {"#": "#3c3c3c"}, "offset": 0}
```
Fills the area with a repeated tile: pixel `(i, j)` in the area = tile character
`rows[j mod th][(i + offset) mod tw]`. `offset` (V) scrolls the pattern.

### `pixels`
```json
{"type": "pixels", "x": 0, "y": 0, "points": [[3, 4, "#ffffff"], [5, 1, "yellow"]]}
```
Individual pixels relative to `x`, `y` (V).

## Order of evaluation per frame

1. Fill the background with `background`.
2. For each layer in order: check `from`/`to`, `blink`, `visible`; draw with `clip`/`wrap`.
3. The result is a `width x height` RGB image.

## Library and API

The server keeps scene files in `scenes/` (`<name>.scene.json`).

| Method | Path | Body | Purpose |
|---|---|---|---|
| GET | `/api/scenes` | – | list `[{name, title, scenes, frames}]` |
| GET | `/api/scenes/<name>` | – | file contents |
| POST | `/api/scenes/<name>` | scene file (JSON) | save / overwrite |
| DELETE | `/api/scenes/<name>` | – | delete |
| POST | `/api/scenes/<name>/play` | – | render on the server and send to the display |
| POST | `/api/scene/play` | scene file (JSON) | render directly and send, without saving |
