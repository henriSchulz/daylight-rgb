# Python library and command line

The package `ko5g` needs Python 3.9+ and Pillow (`pip install -r requirements.txt`).

## Command line

```sh
export KO5G_HOST=<display-ip>                # or pass --display <ip>
python -m ko5g status                        # size, panels, composition, position
python -m ko5g text "Hello" --color 00ff00   # static text on every panel
python -m ko5g text "Hello" --scroll --layout span
python -m ko5g scene scenes/race.scene.json  # render a scene file and send it
python -m ko5g image photo.png --duration 300
python -m ko5g time                          # set the display clock
python -m ko5g switch next                   # next spot (also: prev, next-frame, prev-frame, goto)
python -m ko5g mode auto --repeat 1 2        # playback mode
```

## `ko5g.Display`

```python
from ko5g import Display

d = Display("<display-ip>")          # or Display() with KO5G_HOST set
print(d.info())                      # {"config": ..., "composition": ..., "position": ...}

# one spot with text
d.show_text("Hello", color="ff0000", scroll=True)

# several spots, played one after another
a = d.make_text_spot("ONE", color="00ff00", duration=300)
b = d.make_text_spot("TWO", color="0000ff", duration=300)
d.upload([a, b], mode="auto", params=[1, 1])

d.next_spot(); d.goto(0, 0)          # spot/frame switching (0-based)
d.set_mode("manual_spots")
d.set_time()                         # clock = computer time
```

| Method | Purpose |
|---|---|
| `config` | parsed device configuration (`ko5g.protocol.Config`), read once and cached |
| `info()` | configuration, composition and position as a dict |
| `make_text_spot(text, color, background, scroll, layout, step, duration, font, name)` | render text into a spot |
| `make_image_spot(path, duration, name)` | an image file scaled to fit |
| `make_special_spot(special, background, duration, name)` | special frame (experimental, see protocol.md §5.5) |
| `upload(spots, mode, params, progress, log)` | replace the composition |
| `play_scene(doc)` | render a [ko5g-scene](scene-format.md) document and upload it |
| `show_text(text, **kw)` | shortcut for one text spot |
| `set_mode(mode, params, disabled)` | change the playback mode |
| `next_spot()`, `prev_spot()`, `next_frame()`, `prev_frame()`, `goto(spot, frame)` | switching |
| `set_time(dt=None)` | set the clock |
| `send_fonts()` | upload the vendor font file (needs `tools/extract_vendor_fonts.py`) |

A **spot** is a dict `{"name": str, "frames": [bytes, ...]}` where every element is a complete frame
packet (header + pixel data).

## Building your own frames

```python
from PIL import Image
from ko5g import Display
from ko5g.frames import build_spot

d = Display()
cfg = d.config                                  # width, height, panels(), fragment_order() ...
frames = []
for x in range(cfg.width):
    img = Image.new("RGB", (cfg.width, cfg.height))
    img.putpixel((x, cfg.height // 2), (255, 255, 0))
    frames.append(img)
d.upload([build_spot(cfg, frames, duration=2, name="Dot")])
```

`build_spot(cfg, images, duration, name, special=None, compress=True, merge=True)` sorts the pixels into
the controller's fragment order, compresses each frame (RLE) and merges identical consecutive frames.
`duration` is one value for all frames or a list per frame (units of 10 ms).

Helpers in `ko5g.frames`: `render_static`, `render_scroll`, `text_mask`, `fit_image`, `compose`,
`frame_packet`, `rle_encode` / `rle_decode`, `preview_sheet` (writes a PNG contact sheet).

## Scenes

```python
from ko5g.scene import Renderer, load

doc = load("scenes/race.scene.json")
r = Renderer(doc, 288, 16, Display().config.panels())
images = r.frames(doc["scenes"][0])    # list of PIL images
```

The renderer is the reference implementation of [scene-format.md](scene-format.md); `web/scene.js` renders
identical pixels in the browser.

## Low level: `ko5g.protocol.Connection`

`Connection(host)` sends raw commands (`command(code, payload, expect=...)`), reads configuration,
composition and position, and implements the upload sequence. It retries while the controller is busy
(`wait_ready()`). Command codes and payloads are documented in [protocol.md](protocol.md).
