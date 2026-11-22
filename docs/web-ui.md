# Web UI

A browser front end for the display, served by `ko5g.server` at `/` (default
`http://localhost:8080`). It composes text and animations, shows a live preview that matches the
device pixel for pixel, and sends the result to the display.

The UI text is **German**. All code, comments and these docs are in English.

## What it can do

The page has two tabs that share one LED preview and one send bar.

### Preview

- Draws the display as lit LED dots with a soft glow, at the size the browser window allows. The
  panels reported by the device are drawn flush, as one continuous strip, always in a single row.
- Plays animations at their real frame durations. Pause, step back and step forward are below
  the preview.
- The brightness setting dims the preview too (perceptual curve, not linear).
- The browser renders the exact RGB frames that are sent, so the preview is not an approximation of
  the content, only of how an LED looks.

### Text tab

| Setting | Options |
|---|---|
| Lines | one line, or two lines (two lines only with the small pixel font, 8 px each) |
| Font | `Pixel` (built-in 5x8 font at 2x = 16 px), `Pixel klein` (1x = 8 px), and three system fonts (sans, serif, typewriter) rendered on a canvas and thresholded, with optional anti-aliasing |
| Motion | static, scrolling (8–100 columns per second), blinking (0.5–4 per second) |
| Alignment | left, centre, right (static and blinking text) |
| Colour | single colour, two-colour gradient, rainbow; plus background colour. Swatches are LED-friendly saturated colours; any colour can be picked |
| Layout | same content on every panel, a different content per panel (click a panel in the preview to edit it), or one text across the full width |
| Brightness | fixed 10–100 %, sensor, or off; sent immediately. **Experimental**: the device stores the value but showed no visible change in tests |
| Clock | sets the display clock to the computer's time |

Other details:

- Warnings appear when static text is wider than its panel.
- The last 8 sent designs are kept as thumbnails and can be restored.
- <kbd>Cmd</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> sends.
- The page shows whether the preview is what was last sent from this browser.

### Animations tab

Works with [ko5g-scene](scene-format.md) files.

- **Library**: lists the files on the server (`scenes/`), each with a thumbnail. Clicking an entry
  previews it. For files with several scenes, the preview can play them in display order (with
  `repeat` in `auto` mode) or play one scene on its own.
- **Import**: through a file picker, or by dragging a `.scene.json` file onto the panel. Imported
  files are validated by rendering them.
- **Export**: downloads the current document as `<name>.scene.json`.
- **Save / delete**: stores the current document in the server library. Names may contain only
  `A–Z a–z 0–9 _ -`, at most 64 characters. Overwriting and deleting ask for confirmation.
- **JSON editor**: edits the document directly, and every change is previewed after a short pause.
  JSON and scene errors are shown below the editor.
- **Generate with Claude**: describe an animation in words, or ask for a change to the one shown.
  See [ai-generation.md](ai-generation.md).
- **Send**: posts the document to `POST /api/scene/play`. The server renders it with the Python
  reference interpreter and uploads it. The browser rendering is used only for the preview.

## How it works

All files are plain ES modules in `web/`, with no build step and no dependencies.

| File | Role |
|---|---|
| `index.html`, `styles.css` | markup and styles |
| `app.js` | text tab: state, form binding, rendering, sending, history, brightness, clock, connection handling, tab switching |
| `render.js` | turns the text-tab state into frames (`buildSequence`) |
| `font5x8.js` | the pixel font; also read by `ko5g/scene.py` (see below) |
| `preview.js` | `LedPreview`: draws frames on a canvas as LEDs and plays them |
| `scene.js` | ko5g-scene interpreter (`Renderer`, `renderDoc`), DOM-free |
| `scenes-ui.js` | animations tab: library, preview selection, import/export, editor, AI box |
| `api.js` | HTTP client for `ko5g.server`, mock mode |

### Frames

A frame is a `Uint8Array` of `width × height × 3` bytes, row-major RGB, plus a duration in device
units. One unit is 10 ms (measured on the device). The display size and panel positions come from
`GET /api/status`. Until the server answers, a fallback of 288 × 16 with panels of 128, 64 and
96 columns is used (`api.js`, `FALLBACK_CONFIG`).

**Text tab** (`render.js`):

1. Each zone (a panel, or the whole width) builds an alpha mask of its text, from the pixel font or
   a thresholded canvas font, plus a colour per text column.
2. Animated zones define a tick (scroll: one column per tick; blink: half a period). The fastest
   tick sets the frame duration. The sequence length is the longest cycle, and all scrolling
   zones restart together.
3. Identical consecutive frames are merged by adding up their durations (the server does this as
   well).
4. Static content is one frame of 100 units.
5. Sending posts one spot (`mode: "manual_spots"`) to `POST /api/upload`, with each frame base64
   encoded.

**Animations tab** (`scene.js`) implements [scene-format.md](scene-format.md). It must render
exactly the same pixels as `ko5g/scene.py`, so it copies Python semantics:

- rounding is `floor(v + 0.5)`;
- `//` and `%` are floor division and floor modulo, also for negative numbers;
- a panel index of 0 or below wraps around like a Python list index.

Pixel identity was checked by rendering every frame in Node and in Python and comparing MD5 hashes
per frame. The test set:

- all sample files in `scenes/`;
- a stress scene covering negative values, `wrap`, every easing, `rtl` bars, `flash`, `flip`,
  `clip`, text wider than its region, and non-ASCII glyphs;
- several AI-generated files.

To repeat the check, render a file with `Renderer` from `web/scene.js` in Node and with
`ko5g.scene.Renderer` in Python, then compare the frame bytes.

### The pixel font

`web/font5x8.js` is the single source of the 5×8 font for both interpreters. Python reads it with a
regular expression, so every glyph must stay on its own line in the form

```js
  'X': '.###. #...# ...',
```

The key is in single quotes (escape `'` as `'\''`), and the rows are separated by spaces, 5
characters each, with up to 8 rows. Empty columns are trimmed, which makes the font proportional.
A space is 3 columns wide, and glyphs are separated by 1 column. Unknown characters render as `?`.

### Local storage

The browser keeps its own state in `localStorage` under keys starting with `daylight.`: the
text draft, brightness, the last sent text design, the history, the active tab, and the last sent
animation. Nothing is sent anywhere except to `ko5g.server`.

The page loads the Archivo typeface from Google Fonts. Without network access it falls back to a
system font.

## Mock mode and other origins

- `/?mock` runs the whole UI without server or display. Status and sending are simulated, the
  library is kept in memory, and "generate" returns a placeholder animation.
- `/?api=http://host:port` sends API calls to another origin. `ko5g.server` does not send CORS
  headers, so this only works with a server that allows cross-origin requests. Normally the UI is
  served by `ko5g.server` itself and no option is needed.

## Limits and caveats

- **No authentication.** Anyone who can reach the server can change what the display shows.
  `ko5g.server` binds to `0.0.0.0` by default, so run it only on a trusted network, or bind it to
  `127.0.0.1`. AI generation is restricted to localhost separately.
- Text-tab sequences are capped at 10,000 frames. Upload time is the limit, not storage.
- Brightness has no visible effect yet (see above).
- The preview shows content exactly, but only approximates LED colour, brightness and glow.
- It needs a current browser: ES modules, canvas `roundRect` and `filter`, and CSS `:has()`.
- The UI language is German.
