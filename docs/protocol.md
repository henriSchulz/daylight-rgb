# Ko5G protocol reference

This document describes the network protocol of RGB Technology colour LED controllers that identify
themselves as product **"Ko5G"** (hardware "GIGG", firmware 01.25, protocol generation 5). It was
reconstructed for interoperability from the vendor's Android apps and verified against one real
device (a 288 x 16 px installation made of three panels).

Status markers used below:

- **verified**: tested on the device, behaviour confirmed
- **accepted**: the device acknowledges the command, but the visible effect is unclear or wrong
- **from app**: read from the vendor app, not tested on the device

Everything here is unofficial. Firmware versions other than 01.25 may behave differently.

## 1. Transport

| Item | Value |
|---|---|
| Data port | TCP **2101** (configurable in the web interface, "Data port") |
| Framing | one command per TCP connection: connect, send, read the reply, close |
| Command | ASCII `Ko5G` + 1 command byte + payload |
| Byte order | big endian unless stated otherwise |
| Checksum | none |

The mono variant of the controller uses the header `Mn5G` and a different command table (codes `0xC8`
and up); it is not covered here. A colour controller answers those codes with `c8 c8`.

The controller does not answer commands while it is writing to its SD card (for a few seconds after an
upload). A client should poll a cheap read command (e.g. `0x0D`) until it answers again.

### Short replies

| Reply | Meaning |
|---|---|
| `aa aa` | OK |
| `c8 c8` | unknown command |
| `cc cc` | rejected; e.g. switching to a spot/frame that does not exist |
| `d3 d3` | `SendingRetry` while no upload is in progress |
| *(nothing)* | device busy, or still waiting for more payload bytes |

## 2. Command overview

| Code | Name | Payload (after `Ko5G` + code) | Reply | Status |
|---|---|---|---|---|
| `0x01` | SendConfig | 709 B configuration (§3) | `aa aa` | verified (identical data written back) |
| `0x02` | ReturnConfig | – | 709 B configuration | verified |
| `0x03` | SendFonts | font blob (vendor file) | `aa aa` | accepted |
| `0x04` | ChangeDateTime | 7 B (§7) | `aa aa` | verified |
| `0x06` | SwitchSpotFrame | 5 B (§6) | `aa aa` / `cc cc` | verified |
| `0x07` | NewComp | 8759 B (§5.1) | `aa aa` | verified |
| `0x08` | ReturnComp | – | 10866 B composition (§4) | verified |
| `0x09` | ChangeCompMode | 7731 B (§5.4) | `aa aa` | verified (auto, manual) |
| `0x0B` | AddSpot | 70 B (§5.2) | `aa aa` | verified |
| `0x0C` | ShowAddresses | 1 B on/off | ? | from app |
| `0x0D` | ReturnPosition | – | 63 B (§4.1) | verified |
| `0x10` | SendingRetry | spot (2 B), frame (2 B) | `d3 d3` outside an upload | partly |
| `0x14` | ChangeBrightness | 193 B (§8) | `aa aa` | accepted (no visible effect) |
| `0x16`, `0x17` | ReturnCompV2, ChangeCompModeV2 | – | `c8 c8` | not supported by this firmware |

UDP discovery packets used by the apps (`RGBi`, `RGB?`, Lantronix/Digi module probes) were not tested.

## 3. Configuration (709 bytes, `0x01` / `0x02`)

| Offset | Size | Meaning |
|---|---|---|
| 0 | 1 | height / 8 (pixels) |
| 1 | 1 | width / 16 (pixels) |
| 2 | 1 | board type (index into the geometry table below) |
| 3 | 1 | shape: 0 rectangle, 1 double rectangle, 2 cross, 3 double cross |
| 4 | 8 x 48 | module addresses: 8 ports x 16 entries x 3 B (24 bit) |
| 388 | 128 | fragment map: entry *i* = port + 1 driving address fragment *i* (0 = unused) |
| 516 | 168 | brightness schedule: 7 days (Monday first) x 24 hours, one level per hour |
| 684 | 1 | brightness schedule mode: 1 = daily (day 0 used for all days), 0 = weekly |
| 685 | 2 | brightness curve limits (sensor values) |
| 687 | 2 | brightness curve values (percent) |
| 689 | 20 | unused (zero) |

Board geometry (colour), indexed by board type:

| Board type | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| board width (px) | 16 | 16 | 16 | 16 | 32 | 32 | 32 |
| board height (px) | 8 | 8 | 16 | 16 | 16 | 32 | 32 |
| address fragments across | 1 | 1 | 1 | 1 | 2 | 2 | 2 |
| address fragments down | 1 | 1 | 2 | 2 | 2 | 4 | 4 |

A **fragment** is the area driven by one module address: board width / fragments across by board
height / fragments down (16 x 8 px for board type 4). Fragments are numbered row by row across the whole
display. Physically separate panels show up as runs of fragment columns on different ports.

## 4. Composition (`0x08`, 10866 bytes)

A composition is the playlist stored on the controller: a number of **spots** (animations), each made
of **frames**, plus the playback mode.

| Offset | Size | Meaning |
|---|---|---|
| 0 | 1 | unknown (observed `0x02`) |
| 1 | 2 | number of spots |
| 3 | 1 | mode (see §5.4) |
| 4 + 2i | 2 | number of frames of spot *i* |
| 1028 + 2i | 2 | per-spot parameter: repeat count (auto) or hour, minute (daily) |
| 1028 + 1024d + 2i | 2 | weekly mode: hour, minute of spot *i* on day *d* |
| 10244 + i | 1 | per-spot flags (see §5.4) |

### 4.1 Position (`0x0D`, 63 bytes)

| Offset | Size | Meaning |
|---|---|---|
| 0 | 2 | current spot (0-based) |
| 2 | 2 | current frame within the spot (0-based) |
| 4 | 4 | same values again |
| 8.. | | unknown |

## 5. Uploading content

An upload **replaces the whole composition**. Sequence:

1. `NewComp` (§5.1)
2. for every spot: `AddSpot` (§5.2), then all frames of the spot as one raw stream on a new connection (§5.3).
   The device answers `aa aa` after the last frame.
3. optionally `ChangeCompMode` (§5.4)

Wait until the device answers again after each frame stream before sending the next command.

### 5.1 NewComp (`0x07`)

Payload 8759 bytes, zero-filled:

| Offset | Size | Meaning |
|---|---|---|
| 0 | 1 | height / 8 |
| 1 | 1 | width / 16 |
| 2 | 2 | number of spots |
| 4 | 1 | mode (the vendor app always sends 3 = manual spots and changes it afterwards) |
| 5 + 2i | 2 | number of frames of spot *i* |

### 5.2 AddSpot (`0x0B`)

Payload 70 bytes: spot name at offset 0 as UTF-16LE (ASCII characters at even offsets, up to 34
characters), spot index (0-based) as 2 bytes at offset 68.

### 5.3 Frames

Frames are sent **without** the `Ko5G` header, back to back on one connection, each as:

| Offset | Size | Meaning |
|---|---|---|
| 0 | 2 | frame index within the spot |
| 2 | 1 | compressed flag (1 = RLE, see below) |
| 3 | 1 | special flag (1 = special frame, §5.5) |
| 4 | 2 | length of the pixel data that follows |
| 6 | 2 | duration in units of **10 ms** (verified) |
| 8 | n | pixel data |

**Pixel data** is 8-bit RGB (3 bytes per pixel), ordered **fragment by fragment**:

- the fragments are sent grouped by port (port 1 first), and inside a port in ascending fragment number;
  only fragments that have a port and a non-zero module address are sent
- inside a fragment, the pixels go row by row, left to right

Uncompressed length = width x height x 3.

**Compression** (verified). With the compressed flag set, the pixel data is a sequence of tokens over
RGB pixels:

| Token | Meaning |
|---|---|
| `n, r, g, b` with n ≤ 253 | the pixel (r, g, b) repeated n + 1 times |
| `0xFF, n, ` then (n + 1) x 3 bytes | n + 1 literal pixels (n ≤ 254) |

The tokens decode to exactly width x height x 3 bytes. The vendor app only uses compression when it
saves at least 10 %. Typical animations with a black background shrink by a factor of 13 to 16.

### 5.4 ChangeCompMode (`0x09`)

Payload 7731 bytes:

| Offset | Size | Meaning |
|---|---|---|
| 0 | 1 | mode: 0 auto, 1 daily, 2 weekly, 3 manual spots, 4 manual frames |
| 1 + 2i | 2 | auto: repeat count of spot *i*; daily: hour, minute |
| 1 + 1024d + 2i | 2 | weekly: hour, minute for day *d* (Monday = 0); `ff ff` = off |
| 7169 + i | 1 | flags of spot *i*; unused entries = 7 |

Flag byte: bit 4 = disabled in auto mode; bits 2–3 = weekly state; bits 0–1 = daily state (≥ 2 means
disabled). 0 = enabled everywhere.

Modes: **auto** plays the spots one after another (each *repeat* times), **manual spots** loops the
current spot until it is switched, **daily/weekly** start spots at fixed times. Auto and manual spots were
verified; daily and weekly were not tested.

### 5.5 Special frames (not working yet)

The vendor apps can let the controller draw the time, date, temperature or an analogue clock itself.
Such a frame has the special flag set; its pixel data is padded with zeros to a fixed buffer size
(width x (height / board height) x board width x 3 = 27648 bytes for the tested display; the vendor
app uses the board width for both board dimensions) and followed
by a 66-byte parameter block (enable flags, positions, formats, 8 RGB colours, opacity, fonts, order).
The device acknowledges such frames, but on the tested display it showed garbage on the bottom row
instead of the clock. The parameter block layout is implemented in `ko5g/frames.py` (`Special`) for
further experiments.

## 6. SwitchSpotFrame (`0x06`)

Payload: sub-command (1 B), spot (2 B), frame (2 B).

| Sub | Action |
|---|---|
| 1 / 2 | next / previous spot |
| 3 / 4 | next / previous frame |
| 0 | go to spot, frame (both **0-based**); `cc cc` if it does not exist |

## 7. ChangeDateTime (`0x04`)

Payload: hour, minute, second, weekday (Monday = 0), year mod 100, month, day; one byte each. Verified.

## 8. Brightness (`0x14`)

Payload 193 bytes: the 173-byte block from configuration offsets 516–688 (§3), zero-padded.
Hourly levels: 0 = automatic (light sensor), 1 = 100 %, 2 = 90 % … 10 = 10 %, 11 = off.

The device stores the values (they appear in `ReturnConfig`), but changing the hourly levels had **no
visible effect** on the tested display, not even across an hour boundary. Setting the curve values to
`[10, 10]` with all hours on automatic made the display go dark, and setting them back did not restore it
immediately. Treat this command as experimental.

## 9. Storage

The tested controller stores the composition on an SD card (916 MB). The web interface reports it at
`POST /ajax_memform` (`pMemSize`, error counters). Storing takes about 10 ms per frame. There is no
command to read frame data back, so a composition cannot be downloaded from the device.

## 10. Web interface (port 80)

HTTP Basic authentication (credentials are set by the installer). Read-only status:

- `POST /ajax_mainform` (empty body) → `key=value&...`: network settings, clock, temperature, ambient
  light, display size, mode, firmware, MAC addresses
- `POST /ajax_memform` → SD card statistics

The pages also allow changing network settings, the password and the firmware; this project does not
touch them.

## 11. Open questions

- meaning of the brightness schedule versus the sensor curve
- the special-frame parameter block (clock/date/temperature)
- `ShowAddresses` (`0x0C`), daily/weekly modes, UDP discovery
- the "special frame protocol" port 2102 shown in the web interface (closed on the tested device)
- streaming: `SendingRetry` cannot overwrite frames during playback, so live content needs a full upload
