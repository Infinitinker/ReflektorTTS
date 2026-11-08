# Architecture

## Goal

ReflektorTTS reads an app's text aloud: dialogue, cutscene subtitles and on-screen messages. It translates the text into the user's language on the way, in the style of a Polish *lektor*: one voice speaking over the app's original sound, which is lowered while it speaks.

Its main ideas:

- **A profile per app**: how to recognize the app, where to read its text, how to process it, and a glossary for its names and slang. One profile is one JSON file, so profiles can be shared.
- **A desktop app** next to the clock runs ReflektorTTS, shows what it is doing, manages profiles and downloads voices and translation models.
- **Configuration without leaving the app**, through an overlay. Older games often crash when they lose focus (Alt+Tab).
- **Offline:** voices and translation models run on the user's computer, and nothing is downloaded unless the user asks.
- **Many ways to read text**: an app's memory and its files today; OCR, the clipboard, speech recognition and app function hooks are planned.
- **Plugins** for sources, processing stages, speech engines and downloads.

## Principles

1. **Module ≠ process.** Code is split into modules everywhere, but into separate processes only for isolation, heavy resources (speech models, GPU) or code that must run elsewhere (inside the app).
2. **The core runs headless.** Every user interface, the desktop app's window and the overlay alike, is a client of the same local API.
3. **Logic lives in Python; the overlay only draws.** The C++ code inside the app draws the UI, captures input and will grab frames, nothing more.
4. **Plugins describe their settings with a JSON Schema**, so profiles can be validated and UIs can build forms without knowing the plugin.
5. **Contracts come from real cases.** Interfaces are drawn from the plugins that exist and checked on the next one, not designed ahead for imagined ones.

## Processes

```
 App process                        ReflektorTTS process (Python)                   Child process
                                  ┌─────────────────────────────────────────┐
                                  │ Window and tray icon (desktop app)      │
                                  │        │ commands      ▲ status         │
┌───────────────────┐  API /v1    │        ▼               │                │
│ Overlay (C++ DLL) │◄──────────► │ API server (HTTP + WebSocket)           │
│ draws the panel,  │ 127.0.0.1   │        ▲ commands      │ events         │
│ captures input    │   :47821    │ Core: profiles, app detection,          │
└───────────────────┘             │ settings, event bus                     │
        ▲ loaded by the core      │                                         │
        │ through the injector    │ Sources ──► Stages ──► Sinks            │
                                  │ memory      tracker    tts ─────────────┼──► TTS service
                                  │ avalanche   translate  subtitles        │    (Piper or
                                  │ vlc         pronounce  events (→ API)   │     Windows voices)
                                  └─────────────────────────────────────────┘
```

| Part | Runs in | Why |
|---|---|---|
| Desktop app: window and tray icon | the ReflektorTTS process, on the main thread | it starts the core and stops it on quit; it follows the core through the API, like the overlay |
| Overlay | the app's process | it draws on the app's frames |
| Settings window (`reflektortts-panel`) | a process of its own, started by the desktop app for one profile | it draws the overlay's settings panel (C++), outside any app; it talks to the core through the API, like the overlay |
| Core: profiles, detection, pipeline, API | the ReflektorTTS process, on threads of its own | many small events; calls between processes would only add overhead |
| TTS service | a child process of the core | speech models are heavy and can fail; the core never loads them |

## How a line is read

1. The core watches running processes. When one matches an executable in a profile's `match` (by name, and by SHA-256 where the profile lists builds), it loads the overlay into the app if the profile asks for it (and an overlay build was given), and creates the profile's sources through their plugins. A build the profile does not list is neither read nor given the overlay; the status reports it. A profile whose sources all need an **integration** (a change in the app's own settings, such as VLC's web interface switched on, offered by the source plugin) that is not enabled is not watched for at all: the Profiles tab shows it as not set up, with a button that enables the integration.
2. The runner polls each source on its interval. A source returns the text currently shown, or nothing.
3. Each reading carries the user's **input language** and **output language**. The text passes through that source's stages, e.g. the **tracker**, which passes a line on once it has settled and only once; **replace**, which removes formatting marks; **translate**, which translates the line into the output language when it differs from the input language; **pronounce**, which respells names from the profile's glossary so the voice says them right ("Carl" as "Karl" in Polish); and **normalize**, which spells out numbers, money and percentages in the output language. Each reading passes through the stages twice, in the same order: once for the **text** shown and once for **speech**, each with its own stage objects, so a stage can be on for one and off for the other. The profile says where each stage starts on (`normalize`, for example, only for speech, so subtitles keep the app's own numbers), and the user can switch it on or off for each in the overlay; sources the user switched off are not read.
4. Finished lines go to their output's sinks: the speech result to the **TTS sink**, which sends the line to the TTS service at the chosen speed, which, as the user chose, queues it after the line being spoken (the default; at most 3 lines wait, the oldest dropped first), queues it and speeds up the waiting lines to catch up, or cuts the line being spoken off; the text result to the **subtitles sink**, which, when subtitles are on, publishes it as the subtitle to show and later hides it, after the line has been spoken and read, and to the **events sink**, which publishes it to the event bus, from which the API sends lines and subtitles to the overlay, which draws subtitles over the app.
5. The TTS service tells the core when it starts speaking and when it falls silent, and the core's **ducker** lowers the app's sound for that time, lektor style: it fades the app's own audio sessions down (to 30% by default) and back up half a second after the voice stops, so the app does not pump between close lines. Windows keeps each app's mixer volume between runs, so while an app is lowered its original volume is also kept in a file, and a later run puts it back if this one stopped first.
6. When the app exits, the core closes its sources and waits for the next app.

A failing source, stage or sink is reported once as a `source.error`, `stage.error` or `sink.error` event and never stops the rest. The status carries the error of a failing source, as its message changes, until it works again, so the desktop window's Status tab, which shows it under what ReflektorTTS is doing, and the overlay's panel can say what to do also for an app without the overlay.

## Code map

| Path | Job |
|---|---|
| `src/reflektortts/desktop/` | The desktop app, how ReflektorTTS is run (`ReflektorTTS.exe` in a release): runs the core on a background thread, with a tray icon (pystray) and a window (Tkinter) that follow the core through the local API, like the overlay. The window has a Status tab (what ReflektorTTS is doing, its version and links to the project and its support pages, `about.py`), a Profiles tab (with a group for each integration the selected profile needs, `integration_groups.py`, and whose App settings… button opens the settings window for the selected profile, `panel_window.py`: one window per profile, docked beside the desktop window (`dock.py`, measured through `win32_windows.py` on Windows), brought to the front when asked for again, and closed when ReflektorTTS quits), one tab per kind of download (voices, translations), a Settings tab and a status bar that says what the button under the mouse does. `autostart.py` starts ReflektorTTS, hidden (`--hidden`), when the user signs in to Windows, and `state.py` remembers what the app has told the user (`desktop.json`) |
| `core.py` | The core's main loop and its controls for the API. API requests, the core thread and finished downloads change the core one at a time, under one lock, so each change is made in full |
| `__main__.py` | Runs the core in a console, without the window, so developers see the log as it happens |
| `arguments.py`, `logs.py` | Command line options and where logs go, shared by the desktop app and the console |
| `events.py`, `bus.py` | Event types and the event bus |
| `entry_points.py` | Finds plugins through their Python entry points |
| `glossary.py` | A profile's glossary: its terms, and finding them in a line |
| `integrations.py` | The contract of integrations: changes a source plugin makes in the app's own settings, when the user asks, so it can read the app. Each keeps what it changed in `integrations/<type>.json` in the state folder, to put it back |
| `staging.py` | Staging folders, where downloads are put together before they replace what is installed |
| `pipeline/` | Plugin contracts, the plugin registry and the runner |
| `profiles/` | Profiles: the format (`profile.schema.json`), loading, checking and migrating a file (`loader.py`), which profiles are used, of the bundled ones and the user's own (`catalog.py`), and the bundled profiles (`bundled/`); see [profiles.md](profiles.md) |
| `apps/` | Finds running apps with a profile, and which build each is (`executable.py`) |
| `sources/`, `stages/`, `sinks/` | Built-in plugins. `sources/vlc/` also brings the VLC integration, which turns on VLC's web interface in VLC's own settings file |
| `sinks/tts/` | The tts sink: the core's side of speech (the narrator, which pauses and switches voices, and the client that starts the TTS process; the process runs only while an app is read), and the voice preview, which speaks a sample sentence through a TTS process of its own that exits once it is spoken |
| `tts/` | The TTS service process: its entry point (`process.py`, which imports little, so its log is set up before the engines load), the service, speech engines, playback and voices |
| `downloads/` | Downloads the user asks for: the contract download sources follow, the Piper and Argos sources, and the manager running downloads |
| `process_memory/` | Reading a running app's memory for the sources that need it: the process (one implementation per OS, `windows.py`) and pointer chains |
| `ducking/` | Lowers the app's sound while lines are spoken; the per-app volume has one implementation per OS (`windows.py`, WASAPI audio sessions) |
| `languages.py` | Supported languages and their checks |
| `api/` | The local API (`server.py`), the check that keeps web pages out (`guard.py`) and its error answers (`errors.py`) |
| `settings.py` | Per-user settings: one file per app, and shared ones (the voice remembered for each language, the profiles disabled) |
| `user_dirs.py` | The per-user folders (`%LOCALAPPDATA%\ReflektorTTS` on Windows) |
| `overlay.py` | Loads the overlay into an app |
| `native/` (repository root) | The C++ code, in three parts: `shared/`, a library with the API client and the settings panel's drawing; `overlay/`, the overlay DLL loaded into apps, and its injector; and `panel/`, the settings window: the same settings panel for one profile, in a window of its own (SDL3), started by the desktop app as `reflektortts-panel --profile <id>` with `--dock-*` arguments that open it beside the desktop window, for apps running or not and apps without the overlay. See [native/README.md](../native/README.md) |
| `tests/` (repository root) | Tests, mirroring `src/reflektortts/` |
| `tools/` (repository root) | Developer tools, not part of ReflektorTTS: `draw_icon.py` draws the ReflektorTTS icon, `build_release.py` builds a release (the installer, from `installer.iss`, and the portable zip), `notices.py` collects the licenses it ships, and `sources.py` the source code it offers |

How the folders are organized:

- **Plugin folders** (`sources/`, `stages/`, `sinks/`) hold one plugin each. A plugin is a single module while it is small (`stages/tracker.py`) and becomes a package when it needs several files (`stages/normalize/`, `sources/memory/`, `sinks/tts/`). A plugin with rules for each language keeps them in a `languages/` folder, one module per language named after it (`stages/normalize/languages/polish.py`), so adding a language means adding a file, without changing the plugin's mechanism; the plugin maps language codes to them in one place. Likewise, a plugin that reads several file formats keeps one module per format in a `formats/` folder, whose `__init__.py` picks the module by the file's extension (`sources/vlc/formats/srt.py`).
- **Subsystems** that are not plugins sit at the top level: `pipeline/`, `profiles/`, `apps/`, `api/`, `tts/`, `ducking/`, `desktop/`, and `process_memory/`, which several sources share.
- **Code for a separate process gets its own folder**, so the layout shows what runs where: `tts/` holds the TTS process, and its client in the core lives with the sink in `sinks/tts/`. The core uses from `tts/` only what it shares with the process: the entry point it starts the process with (`process.py`), the contracts and messages (`engine.py`, `service.py`) and the voice listing (`voices.py`, and `available_voices`, which asks each engine plugin for its voices); it never loads a voice.

Writing plugins: [plugins.md](plugins.md). The local API: [api.md](api.md).

## Text sources

| Source | Works without subtitles | Coverage | State |
|---|---|---|---|
| Memory: subtitle buffer (`memory`) | no | per app | Works: GTA2, GTA San Andreas. Needs a static pointer to the text |
| Memory: label of the current line + the app's text table (`avalanche`) | usually | per app | Works for Avalanche's engine (Mad Max): the line's ID from memory, its text in the input language from the game's archives, read in a few seconds in the background as soon as the game is detected. Exact timing, and the text comes from the app's files rather than the screen |
| Media player: the subtitle file of what it plays, at its playback time (`vlc`) | no | VLC media player 3 | Works: reads the subtitle file next to the video (SubRip, WebVTT, ASS/SSA or SBV) at the time VLC's web interface reports, once the VLC integration has turned that interface on. Exact timing, and the text comes from the file rather than the screen; subtitles inside video files are not read |
| OCR | no | any app | Planned. Struggles with colored text and textures; works better on frames grabbed by the overlay |
| Clipboard | depends on the tool | any app with a tool like Textractor | Planned |
| Speech recognition (Whisper) | yes | any app | Planned. Audio of one process (Windows process loopback); about 1–2 s delay. Will check the `Source` contract on a source that pushes text |
| App function hook | yes | per app | Planned. Needs code inside the app (the overlay) |

Finding a line's label when subtitles can be turned off: turn subtitles on and find the text buffer; in Cheat Engine use "Find out what writes to this address" on it; follow it to where the label (or a pointer into the text table) is stored and find a static pointer to it; turn subtitles off and check the value still changes with each line.

## Translation (lektor mode)

- **How it works:** the `translate` stage translates each line from the input language to the output language it carries, only when they differ, and runs before `pronounce` and `normalize`. It splits lines into sentences, because the models are trained on single sentences and drop the rest of longer input, and it remembers recent lines, because apps repeat them. The input language is one the user chooses, English by default; it is not detected, because guessing wrong mistranslates every line (e.g. Polish text run through the English model).
- **Helping the model:** the model copies some sentences instead of translating them, so two kinds are changed for it and changed back after: a sentence in capitals ("GOODBYE!"), whose words it splits into fragments it does not know, is translated in sentence case and its translation put in capitals; one with no ending, as lines an app splits across subtitles have, gets a period, which is taken off its translation. The models take no context beyond one sentence; giving them the previous lines was tried and makes them drop or mix up sentences.
- **The glossary:** the profile's glossary for the line's input language works around the model. A term with a meaning is rewritten in its plain words, and a kept term is swapped for a stand-in name (Kevin, Brian, or Linda for a woman), which the model leaves untranslated but declines, then swapped back. A line of only kept or pronounced terms is not translated. The stand-in names are English, for English input.
- **Output language rules,** in `stages/translate/languages/`: in Polish, a kept term takes the stand-in's ending ("Kevinowi" becomes "Sweetowi", "Kevinem" becomes "Big Smoke'iem"), "z"/"ze" and "w"/"we" before it are fitted to how it begins ("z Kevinem" becomes "ze Sweetem"), and endings the model sets apart from a foreign name ("Frenzy 'ego") are joined to it. In a language without rules a kept term is put back as written.
- **Engine:** Argos Translate's English–Polish model (OPUS-MT based, CC-BY 4.0), run directly with CTranslate2 on the CPU (int8) and tokenized as it was trained (Moses tokens split into BPE subwords, or SentencePiece pieces, whichever tokenizer the package comes with), without the `argostranslate` package and its heavy dependencies. It runs in the core process, at about 0.1 s per line and at most 0.4 s, once per settled line. The model is loaded once and shared by every translate stage, of every source and app. Only an installed model is used, never downloaded by the stage (downloads belong in the desktop app).
- **Why this engine:** an EN→PL benchmark on game lines compared it with Opus-MT `en-zlw` and `tc-bible-big`, Firefox Translations' model (through `fxtranslate`), and Meta's NLLB-200 600M and M2M-100 418M. It gave the most natural translations and was the fastest. Firefox's model needs a Marian-based engine (its SSRU decoder does not run on CTranslate2), and NLLB-200 is licensed for non-commercial use only.
- **Normalization** (the `normalize` stage) covers, in English and Polish: numbers, money, percentages, units after numbers (km, m, kg, min, s, °C…; one-letter units only after a space, so "the 80s" stays a decade), times of day (Polish hours after "o", "do", "przed"… take their case: "o czternastej"), dates with a year ("12.05.2024", "2024-05-12"; without a year "1.5." would be taken for the first of May), common abbreviations and the symbols & and +. In Polish, 1 and 2 take the gender of a following noun common in games ("dwie minuty", "jedną szansę").
- **Planned:** more language pairs; online engines (e.g. DeepL, LLMs) as plugins that can use an app's context; for sources with labels, translating the whole text table ahead of time into a label → translation dictionary, with no delay and room for manual corrections; in normalization, other Polish cases (e.g. "po dwóch minutach", "na ulicę" for "na ul.") and timers such as "02:30", which are read as clock times.

## Overlay

The overlay hooks Direct3D 9, 11 and 12 (DirectDraw and Direct3D 1–8 games work through a wrapper such as dgVoodoo2), draws the ReflektorTTS panel and the subtitles, and blocks the app's input while the panel is open. See [native/README.md](../native/README.md).

Planned:

- A profile editor with forms built from the plugins' schemas.
- Selecting an OCR region and text colors directly on the app's frame, and OCR on frames grabbed from the back buffer (works in fullscreen too).
- Searching the app's memory for text and pointers from inside the app.
- More graphics APIs: OpenGL and Vulkan.

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

## Platforms and distribution

- **Windows** is the main platform. ReflektorTTS ships as an installer and as a portable zip of the same files: the desktop app built with PyInstaller (one folder, its own Python, every dependency included), the settings window, the overlay builds and the notices, built by `tools/build_release.py`, with a zip of the source code it offers next to them. The installer (Inno Setup) installs for the current user, with no administrator rights, or for all users, and asks the user to quit a running ReflektorTTS before an update or removal: `desktop/session.py` holds named mutexes it looks for, which every user may see. User data stays in the per-user folders, so updating replaces only the program folder.
- The desktop app uses Tkinter, part of Python, and pystray (LGPL-3.0) for the tray icon; Qt or wx would look more modern but add over 100 MB. The overlay works only with what is already downloaded: downloads (voices, translation models) belong in the desktop app.
- **Linux** second: apps under Proton/Wine with the same overlay DLL; native apps through a Vulkan layer and `LD_PRELOAD` for OpenGL (as MangoHud does). Sources to port: memory (`process_vm_readv`), OCR (Tesseract), clipboard. Ducking needs a per-app volume through PipeWire/PulseAudio (e.g. `pulsectl`). The settings window (`native/panel/`, SDL3) is portable, but needs a small loopback HTTP/WebSocket transport there in place of WinHTTP before it can be built. pystray and Tkinter both want the main thread on some Linux setups, so the desktop app is checked there separately.
- **macOS** is out of scope: the hardened runtime and SIP block injection, and reading memory (`task_for_pid`) needs extra permissions.
- The core and its UIs stay portable; platform-specific code lives only in plugins and the overlay.

## Open questions

- How community profiles are distributed beyond this repository (e.g. a profile browser in ReflektorTTS).
- Whether the API needs authentication beyond listening only on 127.0.0.1 and refusing web pages (other programs on the machine can still use it).
