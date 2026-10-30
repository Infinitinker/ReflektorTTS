# Architecture

## Goal

ReflektorTTS reads game text aloud: dialogue, cutscene subtitles and on-screen messages. Optionally it translates the text in the style of a Polish *lektor*: one voice speaking over the game's original sound.

Its main ideas:

- **A profile per game**: how to recognize the game, where to read its text, and how to process it. One profile is one JSON file, so profiles can be shared.
- **Configuration without leaving the game**, through an in-game overlay. Older games often crash when they lose focus (Alt+Tab).
- **Many ways to read text**: game memory today; OCR, the clipboard, speech recognition and game function hooks are planned.
- **Plugins** for sources, processing stages, outputs and speech engines.

## Principles

1. **Module ≠ process.** Code is split into modules everywhere, but into separate processes only for isolation, heavy resources (speech models, GPU) or code that must run elsewhere (inside the game).
2. **The core runs headless.** Every user interface, the in-game overlay included, is a client of the same local API.
3. **Logic lives in Python; the overlay only draws.** The C++ code inside the game draws the UI, captures input and will grab frames, nothing more.
4. **Plugins describe their settings with a JSON Schema**, so profiles can be validated and UIs can build forms without knowing the plugin.
5. **Contracts come from real cases.** Interfaces are drawn from the plugins that exist and checked on the next one, not designed ahead for imagined ones.

## Processes

```
 Game process                       Core process (Python, headless)                 Child process
┌───────────────────┐  API /v1    ┌─────────────────────────────────────────┐
│ Overlay (C++ DLL) │◄──────────► │ API server (HTTP + WebSocket)           │
│ draws the panel,  │ 127.0.0.1   │        ▲ commands      │ events         │
│ captures input    │   :47821    │ Core: profiles, game detection,        │
└───────────────────┘             │ settings, event bus                     │
        ▲ loaded by the core      │                                         │
        │ through the injector    │ Sources ──► Stages ──► Sinks            │
                                  │ memory      tracker    tts ─────────────┼──► TTS service
                                  │             replace    events (→ API)   │    (Piper or
                                  └─────────────────────────────────────────┘     Windows voices)
```

| Part | Runs in | Why |
|---|---|---|
| Overlay | the game's process | it draws on the game's frames |
| Core: profiles, detection, pipeline, API | one process | many small events; calls between processes would only add overhead |
| TTS service | a child process of the core | speech models are heavy and can fail; the core never loads them |

## How a line is read

1. The core watches running processes. When one matches a profile's `match.process`, it loads the overlay into the game (if an overlay build was given) and creates the profile's sources through their plugins.
2. The runner polls each source on its interval. A source returns the text currently shown, or nothing.
3. The text passes through that source's stages, e.g. the **tracker**, which passes a line on once it has settled and only once, and **replace**, which removes formatting marks.
4. Finished lines go to every sink: the **TTS sink** sends the line to the TTS service, which cuts off the line still being spoken and speaks the new one; the **events sink** publishes it to the event bus, from which the API sends it to the overlay.
5. When the game exits, the core closes its sources and waits for the next game.

A failing source, stage or sink is reported once as a `source.error`, `stage.error` or `sink.error` event and never stops the rest.

## Code map

| Path | Job |
|---|---|
| `src/reflektortts/__main__.py`, `app.py` | Command line; the core's main loop and its controls for the API |
| `events.py`, `bus.py` | Event types and the event bus |
| `pipeline/` | Plugin contracts, the plugin registry and the runner |
| `profiles/` | Profile schema, loader and migrations |
| `games/detector.py` | Finds running games |
| `sources/`, `stages/`, `sinks/` | Built-in plugins |
| `tts/` | The TTS service process, its client, the narrator and the speech engines |
| `api/server.py` | The local API |
| `settings.py` | Per-user settings |
| `overlay.py` | Loads the overlay into a game |
| `overlay/` | The in-game overlay (C++); see [overlay/README.md](../overlay/README.md) |
| `profiles/` (repository root) | Game profiles; see [profiles/README.md](../profiles/README.md) |

Writing plugins: [plugins.md](plugins.md). The local API: [api.md](api.md).

## Planned

### Text sources

| Source | Works without subtitles | Coverage | Notes |
|---|---|---|---|
| Memory: subtitle buffer | no | per game | **Done.** Needs a static pointer; proven on GTA2 |
| Memory: label of the current line + the game's text table | usually | per game | Text comes from the game's files (e.g. GXT), with exact timing |
| OCR | no | any game | Struggles with coloured text and textures; works better on frames grabbed by the overlay |
| Clipboard | depends on the tool | any game with a tool like Textractor | |
| Speech recognition (Whisper) | yes | any game | Audio of one process (Windows process loopback); about 1–2 s delay. Will check the `Source` contract on a source that pushes text |
| Game function hook | yes | per game | Needs code inside the game (the overlay) |

Finding a line's label when subtitles can be turned off: turn subtitles on and find the text buffer; in Cheat Engine use "Find out what writes to this address" on it; follow it to where the label (or a pointer into the text table) is stored and find a static pointer to it; turn subtitles off and check the value still changes with each line.

### Lektor mode (translation)

- A `translate` stage with replaceable engines: a local model by default, online services as optional plugins.
- For sources with labels: translate the whole text table ahead of time into a label → Polish text dictionary, with no delay and room for manual corrections.
- For OCR and speech recognition: translate as lines arrive, with a cache of translated sentences.
- Polish text normalization (numbers, dates, abbreviations) as a stage, so Polish voices read real game text correctly.

### Overlay

- A profile editor with forms built from the plugins' schemas.
- Selecting an OCR region and text colours directly on the game's frame, and OCR on frames grabbed from the back buffer (works in fullscreen too).
- Searching the game's memory for text and pointers from inside the game.
- Blocking the game's input while the panel is open, through a DirectInput hook (the overlay already handles input through the window procedure and reads mouse buttons directly).
- More graphics APIs: OpenGL and Vulkan (Direct3D 9, 11 and 12 are done). DirectDraw and Direct3D 1–8 games work through a wrapper such as dgVoodoo2.
- A 64-bit build for modern games.

Known pitfalls of older games and how the overlay handles them:

| Problem | Handling |
|---|---|
| Device loss, resolution changes, new swap chains | Follows the newest swap chain or device; handles `Reset` (D3D9); never holds back buffers between frames |
| Games or wrappers destroying their device while others hold references | A replaced device is abandoned, never released |
| Other overlays rewriting code hooks (RTSS, Steam, Discord) | Hooks replace vtable entries instead of patching code |
| Broken render state | State is saved and restored around ImGui |
| DirectInput swallowing clicks | Mouse buttons are read directly |
| The game hides the cursor | ImGui draws its own |
| Anti-cheat in online games | The overlay and memory reading are meant for offline and story modes only |

### Platforms

- **Windows** is the main platform.
- **Linux** second: games under Proton/Wine with the same overlay DLL; native games through a Vulkan layer and `LD_PRELOAD` for OpenGL (as MangoHud does). Sources to port: memory (`process_vm_readv`), OCR (Tesseract), clipboard.
- **macOS** is out of scope: the hardened runtime and SIP block injection, and reading memory (`task_for_pid`) needs extra permissions.
- The core and its UIs stay portable; platform-specific code lives only in plugins and the overlay.

## Open questions

- Which local translation engine to use by default.
- A desktop UI next to the overlay: Qt (PySide6), a web UI served by the core, or none.
- How community profiles are distributed beyond this repository (e.g. a profile browser in the app).
- Whether the API needs authentication beyond listening only on 127.0.0.1.
