# Architecture

## Goal

ReflektorTTS reads an app's text aloud: dialogue, cutscene subtitles and on-screen messages. Optionally it translates the text in the style of a Polish *lektor*: one voice speaking over the app's original sound.

Its main ideas:

- **A profile per app**: how to recognize the app, where to read its text, and how to process it. One profile is one JSON file, so profiles can be shared.
- **Configuration without leaving the app**, through an overlay. Older games often crash when they lose focus (Alt+Tab).
- **Many ways to read text**: app memory today; OCR, the clipboard, speech recognition and app function hooks are planned.
- **Plugins** for sources, processing stages, outputs and speech engines.

## Principles

1. **Module ≠ process.** Code is split into modules everywhere, but into separate processes only for isolation, heavy resources (speech models, GPU) or code that must run elsewhere (inside the app).
2. **The core runs headless.** Every user interface, the overlay included, is a client of the same local API.
3. **Logic lives in Python; the overlay only draws.** The C++ code inside the app draws the UI, captures input and will grab frames, nothing more.
4. **Plugins describe their settings with a JSON Schema**, so profiles can be validated and UIs can build forms without knowing the plugin.
5. **Contracts come from real cases.** Interfaces are drawn from the plugins that exist and checked on the next one, not designed ahead for imagined ones.

## Processes

```
 App process                        Core process (Python, headless)                 Child process
┌───────────────────┐  API /v1    ┌─────────────────────────────────────────┐
│ Overlay (C++ DLL) │◄──────────► │ API server (HTTP + WebSocket)           │
│ draws the panel,  │ 127.0.0.1   │        ▲ commands      │ events         │
│ captures input    │   :47821    │ Core: profiles, app detection,         │
└───────────────────┘             │ settings, event bus                     │
        ▲ loaded by the core      │                                         │
        │ through the injector    │ Sources ──► Stages ──► Sinks            │
                                  │ memory      tracker    tts ─────────────┼──► TTS service
                                  │             replace    events (→ API)   │    (Piper or
                                  └─────────────────────────────────────────┘     Windows voices)
```

| Part | Runs in | Why |
|---|---|---|
| Overlay | the app's process | it draws on the app's frames |
| Core: profiles, detection, pipeline, API | one process | many small events; calls between processes would only add overhead |
| TTS service | a child process of the core | speech models are heavy and can fail; the core never loads them |

## How a line is read

1. The core watches running processes. When one matches an executable in a profile's `match` (by name, and by SHA-256 where the profile lists builds), it loads the overlay into the app if the profile asks for it (and an overlay build was given), and creates the profile's sources through their plugins. A build the profile does not list is neither read nor given the overlay; the status reports it.
2. The runner polls each source on its interval. A source returns the text currently shown, or nothing.
3. Each reading carries the user's **input language** and **output language**. The text passes through that source's stages, e.g. the **tracker**, which passes a line on once it has settled and only once; **replace**, which removes formatting marks; **translate**, which translates the line into the output language when it differs from the input language; **pronounce**, which respells names from the profile's glossary so the voice says them right ("Carl" as "Karl" in Polish); and **normalize**, which spells out numbers, money and percentages in the output language. Each reading passes through the stages twice, in the same order: once for the **text** shown and once for **speech**, each with its own stage objects, so a stage can be on for one and off for the other. The profile says where each stage starts on (`normalize`, for example, only for speech, so subtitles keep the app's own numbers), and the user can switch it on or off for each in the overlay; sources the user switched off are not read.
4. Finished lines go to their output's sinks: the speech result to the **TTS sink**, which sends the line to the TTS service at the chosen speed, which either queues it after the line being spoken (the default; at most 3 lines wait, the oldest dropped first) or cuts that line off; the text result to the **subtitles sink**, which, when subtitles are on, publishes it as the subtitle to show and later hides it, after the line has been spoken and read, and to the **events sink**, which publishes it to the event bus, from which the API sends lines and subtitles to the overlay, which draws subtitles over the app.
5. The TTS service tells the core when it starts speaking and when it falls silent, and the core's **ducker** lowers the app's sound for that time, lektor style: it fades the app's own audio sessions down (to 30% by default) and back up half a second after the voice stops, so the app does not pump between close lines. Windows keeps each app's mixer volume between runs, so while an app is lowered its original volume is also kept in a file, and a later run puts it back if this one stopped first.
6. When the app exits, the core closes its sources and waits for the next app.

A failing source, stage or sink is reported once as a `source.error`, `stage.error` or `sink.error` event and never stops the rest.

## Code map

| Path | Job |
|---|---|
| `src/reflektortts/__main__.py`, `core.py` | Command line; the core's main loop and its controls for the API. API requests, the core thread and finished downloads change the core one at a time, under one lock, so each change is made in full |
| `arguments.py`, `logs.py` | Command line options and where logs go, shared by the command line and the desktop app |
| `desktop/` | The desktop app: runs the core on a background thread, with a tray icon (pystray) and a window (Tkinter) that follow the core through the local API, like the overlay. The window has a Status tab, a Profiles tab, one tab per kind of download (voices, translations) and a status bar that says what the button under the mouse does |
| `events.py`, `bus.py` | Event types and the event bus |
| `pipeline/` | Plugin contracts, the plugin registry and the runner |
| `profiles/` | Profiles: the format (`profile.schema.json`), loading, checking and migrating a file (`loader.py`), which profiles are used, of the bundled ones and the user's own (`catalog.py`), and the bundled profiles (`bundled/`); see [profiles.md](profiles.md) |
| `apps/` | Finds running apps with a profile, and which build each is (`executable.py`) |
| `sources/`, `stages/`, `sinks/` | Built-in plugins |
| `sinks/tts/` | The tts sink: the core's side of speech (the narrator, which pauses and switches voices, and the client that starts the TTS process; the process runs only while an app is read), and the voice preview, which speaks a sample sentence through a TTS process of its own that exits once it is spoken |
| `tts/` | The TTS service process: speech engines, playback and voices |
| `downloads/` | Downloads the user asks for: the contract download sources follow, the Piper and Argos sources, and the manager running downloads |
| `process_memory/` | Reading a running app's memory for the sources that need it: the process (one implementation per OS, `windows.py`) and pointer chains |
| `ducking/` | Lowers the app's sound while lines are spoken; the per-app volume has one implementation per OS (`windows.py`, WASAPI audio sessions) |
| `languages.py` | Supported languages and their checks |
| `api/` | The local API (`server.py`), the check that keeps web pages out (`guard.py`) and its error answers (`errors.py`) |
| `settings.py` | Per-user settings: one file per app, and shared ones (the voice remembered for each language, the profiles disabled) |
| `user_dirs.py` | The per-user folders (`%LOCALAPPDATA%\ReflektorTTS` on Windows) |
| `overlay.py` | Loads the overlay into an app |
| `overlay/` (repository root) | The overlay (C++); see [overlay/README.md](../overlay/README.md) |
| `tests/` (repository root) | Tests, mirroring `src/reflektortts/` |
| `tools/` (repository root) | Developer tools, not part of ReflektorTTS: `draw_icon.py` draws the ReflektorTTS icon |

How the folders are organized:

- **Plugin folders** (`sources/`, `stages/`, `sinks/`) hold one plugin each. A plugin is a single module while it is small (`stages/tracker.py`) and becomes a package when it needs several files (`stages/normalize/`, `sources/memory/`, `sinks/tts/`). A plugin with rules for each language keeps them in a `languages/` folder, one module per language named after it (`stages/normalize/languages/polish.py`), so adding a language means adding a file, without changing the plugin's mechanism; the plugin maps language codes to them in one place.
- **Subsystems** that are not plugins sit at the top level: `pipeline/`, `profiles/`, `apps/`, `api/`, `tts/`, `ducking/`, `desktop/`, and `process_memory/`, which several sources share.
- **A folder's code runs in one process.** Code for a separate process gets its own folder, so the layout shows what runs where: `tts/` is the TTS process, and its client in the core lives with the sink in `sinks/tts/`.

Writing plugins: [plugins.md](plugins.md). The local API: [api.md](api.md).

## Planned

### Text sources

| Source | Works without subtitles | Coverage | Notes |
|---|---|---|---|
| Memory: subtitle buffer | no | per app | **Done.** Needs a static pointer; proven on GTA2 |
| Memory: label of the current line + the app's text table | usually | per app | Text comes from the app's files (e.g. GXT), with exact timing. **Done** for Avalanche's engine (Mad Max, `avalanche` source): the line's ID from memory, its text in the input language from the game's archives, read in a few seconds in the background as soon as the game is detected |
| OCR | no | any app | Struggles with colored text and textures; works better on frames grabbed by the overlay |
| Clipboard | depends on the tool | any app with a tool like Textractor | |
| Speech recognition (Whisper) | yes | any app | Audio of one process (Windows process loopback); about 1–2 s delay. Will check the `Source` contract on a source that pushes text |
| App function hook | yes | per app | Needs code inside the app (the overlay) |

Finding a line's label when subtitles can be turned off: turn subtitles on and find the text buffer; in Cheat Engine use "Find out what writes to this address" on it; follow it to where the label (or a pointer into the text table) is stored and find a static pointer to it; turn subtitles off and check the value still changes with each line.

### Lektor mode (translation)

- **Done:** the `translate` stage translates each line from the input language to the output language it carries, only when they differ, and runs before `normalize`. It splits lines into sentences, because the models are trained on single sentences and drop the rest of longer input, and it remembers recent lines, because apps repeat them. The model copies some sentences instead of translating them, so two kinds are changed for it and changed back after: a sentence in capitals ("GOODBYE!"), whose words it splits into fragments it does not know, is translated in sentence case and its translation put in capitals; one with no ending, as lines an app splits across subtitles have, gets a period, which is taken off its translation. The profile's glossary works around the model: a term with a meaning is rewritten in its plain words, and a kept term is swapped for a stand-in name (Kevin, Brian, or Linda for a woman), which the model leaves untranslated but declines, then swapped back with the stand-in's ending ("Kevinowi" becomes "Sweetowi"). Recent translations are remembered per glossary. The input language is one the user chooses, English by default; it is not detected, because guessing wrong mistranslates every line (e.g. Polish text run through the English model).
- **Engine:** Argos Translate's English–Polish model (OPUS-MT based, CC-BY 4.0), run directly with CTranslate2 on the CPU (int8) and tokenized as it was trained (Moses tokens split into BPE subwords, or SentencePiece pieces, whichever tokenizer the package comes with), without the `argostranslate` package and its heavy dependencies. It runs in the core process, at about 0.1 s per line and at most 0.4 s, once per settled line. The model is loaded once and shared by every translate stage, of every source and app. The packages are the optional `translate` extra; only an installed model is used, never downloaded by the stage (downloads belong in the desktop app).
- **Why this engine:** an EN→PL benchmark on game lines compared it with Opus-MT `en-zlw` and `tc-bible-big`, Firefox Translations' model (through `fxtranslate`), and Meta's NLLB-200 600M and M2M-100 418M. It gave the most natural translations and was the fastest. Firefox's model needs a Marian-based engine (its SSRU decoder does not run on CTranslate2), and NLLB-200 is licensed for non-commercial use only.
- Planned: more language pairs; a glossary per profile for names and terms (offline models take no context, so names would be swapped for placeholders and back); online engines (e.g. DeepL, LLMs) as optional plugins that can use an app's context.
- For sources with labels: translate the whole text table ahead of time into a label → Polish text dictionary, with no delay and room for manual corrections.
- Normalization covers, in English and Polish: numbers, money, percentages, units after numbers (km, m, kg, min, s, °C…; one-letter units only after a space, so "the 80s" stays a decade), times of day (Polish hours after "o", "do", "przed"… take their case: "o czternastej"), dates with a year ("12.05.2024", "2024-05-12"; without a year "1.5." would be taken for the first of May), common abbreviations and the symbols & and +. In Polish, 1 and 2 take the gender of a following noun common in games ("dwie minuty", "jedną szansę"). Still to come: other cases (e.g. "po dwóch minutach", "na ulicę" for "na ul."), and timers such as "02:30", which are read as clock times.
- The translate stage joins the endings Polish gives foreign names ("Frenzy'ego"), which the detokenizer leaves apart.

### Overlay

- A profile editor with forms built from the plugins' schemas.
- Selecting an OCR region and text colors directly on the app's frame, and OCR on frames grabbed from the back buffer (works in fullscreen too).
- Searching the app's memory for text and pointers from inside the app.
- More graphics APIs: OpenGL and Vulkan (Direct3D 9, 11 and 12 are done). DirectDraw and Direct3D 1–8 games work through a wrapper such as dgVoodoo2.

Known pitfalls of older games and how the overlay handles them:

| Problem | Handling |
|---|---|
| Device loss, resolution changes, new swap chains | Follows the newest swap chain or device; handles `Reset` (D3D9); never holds back buffers between frames |
| Games or wrappers destroying their device while others hold references | A replaced device is abandoned, never released |
| Other overlays hooking the same methods (Steam, RTSS, Discord) | Methods are hooked in their code, as those overlays do, so all the hooks chain; a replaced vtable entry looped with the Steam overlay's hook |
| Other overlays removing their hook on each call, and ours with it (RTSS) | The overlay checks its hooks twice a second and, when one was cut out, hooks the other overlay's code instead |
| Games keeping a method's address instead of reading the vtable | Code hooks catch those calls too |
| The game drawing on a different thread than its window's | Window messages for the panel wait until the drawing thread's next frame |
| ImGui leaving some Direct3D 11 state unbound (hull, domain and compute shaders, extra render targets) | The overlay saves and restores it around ImGui |
| Broken render state | State is saved and restored around ImGui |
| DirectInput swallowing clicks | Mouse buttons are read directly |
| The game reacting to keys and clicks meant for the panel | While the panel is open, the game's keyboard and mouse input is blocked (DirectInput, the message queue, key state, raw input, the cursor), as ReShade does; gamepads still work |
| The game hides the cursor | ImGui draws its own |
| Anti-cheat in online games | The overlay and memory reading are meant for offline and story modes only |

### Platforms

- **Windows** is the main platform.
- **Linux** second: apps under Proton/Wine with the same overlay DLL; native apps through a Vulkan layer and `LD_PRELOAD` for OpenGL (as MangoHud does). Sources to port: memory (`process_vm_readv`), OCR (Tesseract), clipboard. Ducking needs a per-app volume through PipeWire/PulseAudio (e.g. `pulsectl`).
- **macOS** is out of scope: the hardened runtime and SIP block injection, and reading memory (`task_for_pid`) needs extra permissions.
- The core and its UIs stay portable; platform-specific code lives only in plugins and the overlay.
- On Windows, ReflektorTTS ships as a portable zip: the desktop app built with PyInstaller (one folder, its own Python), the overlay builds and the notices, built by `tools/build_release.py`. User data stays in the per-user folders, so a release folder can be replaced to update. An installer may follow.
- The desktop app uses Tkinter, part of Python, and pystray (LGPL-3.0) for the tray icon; Qt or wx would look more modern but add over 100 MB. The overlay works only with what is already downloaded: downloads (voices, translation models) belong in the desktop app. pystray and Tkinter both want the main thread on some Linux setups, so the window is checked there separately.

## Open questions

- How community profiles are distributed beyond this repository (e.g. a profile browser in ReflektorTTS).
- Whether the API needs authentication beyond listening only on 127.0.0.1 and refusing web pages (other programs on the machine can still use it).
