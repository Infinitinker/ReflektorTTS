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
3. Each reading carries the player's **game language** and **speech language**. The text passes through that source's stages, e.g. the **tracker**, which passes a line on once it has settled and only once; **replace**, which removes formatting marks; **translate**, which translates the line into the speech language when it differs from the game language; and **normalize**, which spells out numbers, money and percentages in the speech language. Stages the player switched off in the overlay are skipped.
4. Finished lines go to every sink: the **TTS sink** sends the line to the TTS service, which cuts off the line still being spoken and speaks the new one; the **events sink** publishes it to the event bus, from which the API sends it to the overlay.
5. The TTS service tells the core when it starts speaking and when it falls silent, and the core's **ducker** lowers the game's sound for that time, lektor style: it fades the game's own audio sessions down (to 30% by default) and back up half a second after the voice stops, so the game does not pump between close lines. Windows keeps each app's mixer volume between runs, so while a game is lowered its original volume is also kept in a file, and a later run puts it back if this one stopped first.
6. When the game exits, the core closes its sources and waits for the next game.

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
| `sinks/tts/` | The tts sink: the core's side of speech (the narrator, which pauses and switches voices, and the client that starts the TTS process) |
| `tts/` | The TTS service process: speech engines, playback and voices |
| `ducking/` | Lowers the game's sound while lines are spoken; the per-app volume has one implementation per OS (`windows.py`, WASAPI audio sessions) |
| `languages.py` | Supported languages and their checks |
| `api/server.py` | The local API |
| `settings.py` | Per-user settings |
| `overlay.py` | Loads the overlay into a game |
| `overlay/` (repository root) | The in-game overlay (C++); see [overlay/README.md](../overlay/README.md) |
| `profiles/` (repository root) | Game profiles; see [profiles/README.md](../profiles/README.md) |
| `tests/` (repository root) | Tests, mirroring `src/reflektortts/` |

How the folders are organized:

- **Plugin folders** (`sources/`, `stages/`, `sinks/`) hold one plugin each. A plugin is a single module while it is small (`stages/tracker.py`) and becomes a package when it needs several files (`stages/normalize/`, `sources/memory/`, `sinks/tts/`).
- **Subsystems** that are not plugins sit at the top level: `pipeline/`, `profiles/`, `games/`, `api/`, `tts/`, `ducking/`.
- **A folder's code runs in one process.** Code for a separate process gets its own folder, so the layout shows what runs where: `tts/` is the TTS process, and its client in the core lives with the sink in `sinks/tts/`.

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

- **Done:** the `translate` stage translates each line from the game language to the speech language it carries, only when they differ, and runs before `normalize`. It splits lines into sentences, because the models are trained on single sentences and drop the rest of longer input, and it remembers recent lines, because games repeat them. `auto` is taken as English while English is the only source language.
- **Engine:** Argos Translate's English–Polish model (OPUS-MT based, CC-BY 4.0), run directly with CTranslate2 on the CPU (int8) and tokenized as it was trained (Moses tokens, BPE subwords), without the `argostranslate` package and its heavy dependencies. It runs in the core process, at about 0.1 s per line and at most 0.4 s, once per settled line. The packages are the optional `translate` extra; the model is downloaded on first use.
- **Why this engine:** an EN→PL benchmark on game lines compared it with Opus-MT `en-zlw` and `tc-bible-big`, Firefox Translations' model (through `fxtranslate`), and Meta's NLLB-200 600M and M2M-100 418M. It gave the most natural translations and was the fastest. Firefox's model needs a Marian-based engine (its SSRU decoder does not run on CTranslate2), and NLLB-200 is licensed for non-commercial use only.
- Planned: more language pairs; a glossary per profile for names and game terms (offline models take no context, so names would be swapped for placeholders and back); online engines (e.g. DeepL, LLMs) as optional plugins that can use a game's context.
- For sources with labels: translate the whole text table ahead of time into a label → Polish text dictionary, with no delay and room for manual corrections.
- Normalization covers numbers, money and percentages in English and Polish so far; dates, times and abbreviations (the PoC had Polish rules for them) are still to come.

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
- **Linux** second: games under Proton/Wine with the same overlay DLL; native games through a Vulkan layer and `LD_PRELOAD` for OpenGL (as MangoHud does). Sources to port: memory (`process_vm_readv`), OCR (Tesseract), clipboard. Ducking needs a per-app volume through PipeWire/PulseAudio (e.g. `pulsectl`).
- **macOS** is out of scope: the hardened runtime and SIP block injection, and reading memory (`task_for_pid`) needs extra permissions.
- The core and its UIs stay portable; platform-specific code lives only in plugins and the overlay.

## Open questions

- A desktop UI next to the overlay: Qt (PySide6), a web UI served by the core, or none.
- How community profiles are distributed beyond this repository (e.g. a profile browser in the app).
- Whether the API needs authentication beyond listening only on 127.0.0.1.
