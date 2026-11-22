# daylight-rgb

Open control software for **RGB Technology colour LED signs** (controller "Ko5G"): show any text,
images and pixel animations over Ethernet, from the command line, a Python library, an HTTP API or a
browser UI.

The vendor only ships apps that switch between pre-loaded content. This project talks to the controller
directly, with a protocol that was reconstructed for interoperability and documented in
[docs/protocol.md](docs/protocol.md).

> Not affiliated with or endorsed by RGB Technology. Product names are trademarks of their owners.
> Uploading content **replaces everything stored on the sign**, and the original content cannot be read
> back. Use at your own risk.

## Features

- Static, scrolling and blinking text in any colour, per physical panel or across the whole sign
- Images and frame-by-frame animations (8-bit RGB, 10 ms timing resolution)
- Several animations in rotation (auto mode) or switched by hand
- **ko5g-scene**: a small JSON format that describes animations (sprites, text, bars, keyframes)
  instead of storing frames; rendered pixel-identically in Python and in the browser
- Browser UI with live LED preview, animation library, editor, import/export
- Optional AI generation of scenes from a text prompt via the Claude CLI
- Fast uploads: run-length compression and frame merging (about 10 ms per frame)
- Set the sign's clock, read its configuration and status

## Quick start

```sh
git clone https://github.com/henriSchulz/daylight-rgb.git && cd daylight-rgb
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export KO5G_HOST=<display-ip>

.venv/bin/python -m ko5g status                          # check the connection
.venv/bin/python -m ko5g text "Hello" --color 00ff00 --scroll
.venv/bin/python -m ko5g scene scenes/race.scene.json

.venv/bin/python -m ko5g.server --bind 127.0.0.1         # web UI at http://localhost:8080
```

Network setup (static IP on the computer, finding the sign): [docs/hardware-setup.md](docs/hardware-setup.md).

## Documentation

| Document | Content |
|---|---|
| [hardware-setup.md](docs/hardware-setup.md) | the tested sign, network connection, web interface |
| [protocol.md](docs/protocol.md) | the controller protocol: commands, upload, pixel order, compression |
| [python-library.md](docs/python-library.md) | `python -m ko5g` and the `ko5g` package |
| [http-api.md](docs/http-api.md) | the JSON API of `ko5g.server` |
| [scene-format.md](docs/scene-format.md) | the ko5g-scene animation format |
| [web-ui.md](docs/web-ui.md) | the browser UI |
| [ai-generation.md](docs/ai-generation.md) | generating scenes with the Claude CLI |

## Status

| Function | State |
|---|---|
| Read configuration, composition, position | works |
| Upload text, images, animations, several spots | works |
| Compression, frame merging | works |
| Auto and manual playback modes, spot/frame switching | works |
| Set the clock | works |
| Write configuration | works (tested by writing back identical data) |
| Daily/weekly schedules | implemented, not tested on a device |
| Brightness | stored by the device, **no visible effect** yet |
| Clock/date/temperature drawn by the controller ("special frames") | **not working yet** |
| Live streaming | not possible with the known protocol (every upload replaces the content) |

Tested with one sign: 288 x 16 px made of three panels, firmware 01.25. Reports from other sizes and
firmware versions are welcome.

## TODO

- [ ] **Art-Net interface**: accept Art-Net (DMX over UDP) so lighting consoles and tools such as
  xLights can drive the sign. Open question: the known protocol cannot stream, because every upload
  replaces the stored content, so this needs either a streaming mode in the controller or a bridge
  that turns Art-Net input into short uploads.
- [ ] **Wireless connection**: control the sign over Wi-Fi instead of Ethernet, through the
  controller's own access point or by joining it to an existing network.
- [ ] **Android app**: a phone app for text, animations and the library, built on the HTTP API.

## Project layout

```
ko5g/            Python package
  protocol.py      controller protocol (commands, upload, config parsing)
  frames.py        pixel order, compression, text/image rendering
  scene.py         reference renderer for the ko5g-scene format
  server.py        HTTP API + static web UI
  ai.py            scene generation via the Claude CLI
  __main__.py      command line interface
web/             browser UI (no build step)
scenes/          example animations (*.scene.json)
animations/      Python sources of the example animations and their converter to scenes
tools/           helper scripts (vendor font extraction)
docs/            documentation
```

## Security

`ko5g.server` has no authentication: anyone who can reach it can change the sign. Bind it to
`127.0.0.1` (`--bind 127.0.0.1`) or run it only in a trusted network. AI generation is limited to the
local computer by default ([ai-generation.md](docs/ai-generation.md#security)). The web UI loads a font
from Google Fonts.

## How the protocol was found

The controller exposes a TCP data port but no documentation. The command set, the pixel order and the
compression were read from the vendor's freely available Android apps ("RGB Switcher", "RGB Cross") for
the purpose of interoperability and then verified against a real sign. This repository contains no
vendor code or vendor files. The font file used by command `0x03` can be extracted from your own copy of
the vendor app with `tools/extract_vendor_fonts.py`.

## License

[MIT](LICENSE)
