# AI generation

`ko5g.server` can have Claude write [ko5g-scene](scene-format.md) animations from a short
description. It runs the [Claude Code](https://claude.com/claude-code) command-line
tool on the machine where the server runs. The result is an ordinary scene file: it is previewed
in the browser and sent or saved like any other animation. Generation never talks to the display.

Code: `ko5g/ai.py`, plus the `/api/generate` branch in `ko5g/server.py`.

## Requirements

- Claude Code installed and logged in for the user who runs the server. Check with
  `claude auth status`. The executable is looked up on `PATH`, then at `~/.local/bin/claude`.
- Tested with Claude Code 2.1.

**Billing.** The CLI uses whatever credentials it has:

- When logged in with a Claude subscription, each generation counts towards that plan's usage
  limits.
- When `ANTHROPIC_API_KEY` is set in the server's environment, the CLI uses the key instead and
  calls are billed per token.

## Using it

**In the web UI**: open the *Animationen* tab, describe the animation in the box at the top and
press *Erzeugen* (or <kbd>Enter</kbd>). Once a document is loaded, a checkbox switches to changing
the animation shown instead of creating a new one, for example "make the boat red". The result
appears in the preview as unsaved.

**From the command line** (prints the scene JSON to stdout and a summary to stderr):

```sh
.venv/bin/python -m ko5g.ai "two small robots play table tennis" > robots.scene.json
```

**Over HTTP**:

```
POST /api/generate
{"prompt": "…", "scene": {…optional current document…}, "model": "optional model name"}

200 {"ok": true, "scene": {…}, "attempts": 1, "cost_usd": 0.15, "seconds": 54.5, "frames": 400}
```

| Status | Meaning |
|---|---|
| 400 | invalid `model` name or `scene` is not an object |
| 403 | request not from localhost (see [Security](#security)) |
| 409 | another generation is running (`error` starts with `busy`) |
| 422 | empty or too long prompt, the CLI failed, or no valid animation after the repair rounds |
| 500 | unexpected server error |

A call takes about a minute, so the web client waits up to 10 minutes.

## How it works

1. **Checks.** The request must come from localhost. The prompt must not be empty and must have
   at most 2,000 characters. Only one generation runs at a time, guarded by a lock of its own.
2. **Display facts.** Width, height and panels are read from the device configuration, under the
   display lock but only briefly. The generation itself runs outside that lock, so the display
   API stays usable meanwhile.
3. **CLI call.** The tool runs in an empty temporary directory, with no shell, so no project
   files are in reach:

   ```
   claude -p --output-format json --tools "" --strict-mcp-config --no-session-persistence \
          --system-prompt "<system prompt>" [--model <model>] "<user message>"
   ```

   | Flag | Why |
   |---|---|
   | `-p --output-format json` | non-interactive; the answer and metadata come back as JSON (`result`, `is_error`, `total_cost_usd`) |
   | `--tools ""` | no built-in tools at all; the model can only write text |
   | `--strict-mcp-config` | no MCP servers from the user's configuration |
   | `--no-session-persistence` | the call is not saved as a resumable session |
   | `--system-prompt` | replaces the default Claude Code system prompt |

   Each call times out after 240 seconds.
4. **System prompt** (built per call, summary):
   - the role: design animations for an RGB LED sign and answer with exactly one ko5g-scene
     version 1 JSON document, with no prose and no code fences;
   - the display: size, panel positions (the panels sit flush), and frame timing;
   - the glyphs the pixel font supports, and how wide text is at scale 1 and 2;
   - limits to stay within: frames per scene, fps 8–30, sprite height;
   - design guidance for LEDs: black background, saturated colours, readable horizontal text
     speeds, seamless loops, use of the wide format;
   - the **originality rule**: only original figures and designs, never characters, logos,
     mascots or levels from existing games, films, comics or brands, even if the request names
     them; instead an original figure in the same spirit;
   - when a current document is passed: change it as requested and return the whole document;
   - the full text of [scene-format.md](scene-format.md).

   The user message is the prompt. For a change it also contains the current document after the
   line `CURRENT DOCUMENT:`.
5. **Parsing.** The JSON object is taken from the answer: inside a code fence if there is one,
   otherwise from the first `{` to the last `}`.
6. **Validation.** Every frame of every scene is rendered with the reference interpreter
   (`ko5g.scene.Renderer`). This catches unknown colours, sprites without a colour for a
   character, bad values, and similar errors. On top of that:

   | Limit | Value |
   |---|---|
   | scenes per file | ≤ 20 |
   | frames per scene | ≤ 1,200 |
   | frames in total | ≤ 10,000 |
   | fps | 1–50 |
   | something visible | at least one frame must differ from the plain background |

7. **Repair rounds.** If parsing or validation fails, the model gets the original request, its
   previous answer and the error message, and is asked for a corrected complete document. There
   are up to 2 repair rounds, so at most 3 CLI calls per request.

## Measurements

These were made with the CLI's default model at the time.

| Prompt | Attempts | Time | Frames | `cost_usd` |
|---|---|---|---|---|
| a sailboat at sunset with gulls | 1 | 54 s | 400 | 0.145 |
| two pixel robots play table tennis | 1 | 75 s | 440 | 0.149 |

`cost_usd` is the API-price equivalent that the CLI reports. With a subscription it is not
charged; it only shows the relative size of a call. The web UI does not display it.

## Security

- **Localhost only.** `ko5g.server` binds to `0.0.0.0` by default. Otherwise anyone on the network
  could start CLI calls on the owner's account, so `/api/generate` answers 403 to every client
  except `127.0.0.1` and `::1`. Start the server with `--allow-remote-generate` to lift the
  restriction, and do that only on a network you trust.
- **No tools.** The model cannot run commands, read files or use MCP servers. It only returns text.
- **Data, not code.** A scene file only describes drawing. It is validated and rendered by the
  interpreters and never executed.
- **Bounded work.** The prompt length, frame limits, one generation at a time and the CLI timeout
  keep a single request from tying up the server.
- The `model` field must match `^[a-z][a-z0-9.\-\[\]]{0,63}$`, so it cannot be used to pass
  extra command-line options.
