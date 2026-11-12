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
2. **The core runs headless.** Every user interface, the ReflektorTTS window and the overlay alike, is a client of the same local API.
3. **Logic lives in Python; the overlay only draws.** The C++ code inside the app draws the UI, captures input and will grab frames, nothing more.
4. **Plugins describe their settings with a JSON Schema**, so profiles can be validated and UIs can build forms without knowing the plugin.
5. **Contracts come from real cases.** Interfaces are drawn from the plugins that exist and checked on the next one, not designed ahead for imagined ones.

## Terms

Each concept has one name, used in the interface, the code, file names, settings, the API, the docs and commit messages. A new concept gets its name here first. Where the interface words a concept for users, the table says so.

| Term | Meaning | In the code |
|---|---|---|
| app | A program ReflektorTTS reads: a game or a media player. "Game" is used only for what concerns games alone | `app` in a profile and in the status, `apps/` |
| profile | One JSON file that describes one app: how to recognize it, where to read its text, how to process it, and its glossary. A profile is bundled with ReflektorTTS or the user's own; the interface says **Bundled**, **Your own** and **Your own (replaces bundled)**, which the API's `origin` calls `bundled`, `custom` and `override` | `profiles/`, `Profile`, `profile.schema.json`, `Origin` in `profiles/catalog.py` |
| build | One version of an app's executable, told apart by its SHA-256. A profile can list the builds it was tested with; a build it does not list is neither read nor given the overlay. The interface says **version** | `sha256` in a profile's `match`, `apps/executable.py`, `Builds` in `apps/detector.py`, `unsupported` in the status |
| rating | How far a profile is tested: bronze, silver, gold or platinum, shown as a medal | `rating` in a profile, `desktop/tabs/medals.py` |
| profile settings | What the user chooses for one app: the languages, the voice, how lines are spoken and shown, and which sources and stages are on. The interface opens them with **App settings…** | `ProfileSettings` in `settings.py`, `/v1/profiles/<id>/settings` |
| plugin | A part found through its Python entry point, so adding one changes neither the core nor the interface: a source, a stage, a speech engine or a download source | `entry_points.py`, each plugin's `PLUGIN`, the entry-point groups `reflektortts.sources`, `reflektortts.stages`, `reflektortts.tts_engines` and `reflektortts.downloads` |
| source | A plugin that reads an app's text when polled: `memory`, `avalanche`, `vlc` | `Source` in `pipeline/protocols.py`, `sources/` |
| stage | A plugin that changes or drops a line on its way to the sinks: `tracker`, `replace`, `translate`, `pronounce`, `normalize` | `Stage` in `pipeline/protocols.py`, `stages/` |
| sink | Where finished lines go: `tts` speaks them, `subtitles` shows them over the app, `events` publishes them on the event bus | `Sink` in `pipeline/protocols.py`, `sinks/` |
| line | One piece of an app's text, as a source reads it and as it is spoken and shown | `TextEvent` in `events.py` |
| output | What a line is prepared for: the **text** shown, or **speech**. Each source's stages run once for each, so a stage can be on for one and off for the other | `Output` in `events.py`, `text` and `speech` in a profile's stages |
| input language, output language | The language of the app's text, and the language lines are prepared, spoken and shown in, both chosen by the user. The interface calls each **Language**, under Input and Output | `input_language`, `output_language`, `languages.py` |
| subtitles | Lines shown over the app by the overlay | `sinks/subtitles.py`, `SubtitleEvent`, `native/overlay/src/ui/subtitles.cpp` |
| glossary | A profile's words and phrases that translation and speech treat specially, for each input language. Each entry is a **term**, which is kept (never translated), has a meaning (the plain words it is translated as) or is pronounced (respelled for an output language) | `glossary` in a profile, `glossary.py` (`GlossaryTerm`), `stages/translate/glossary.py` |
| stand-in | A name the translate stage swaps a kept term for, which the model leaves untranslated but declines, and which is then swapped back | `MALE_STAND_INS` and `FEMALE_STAND_INS` in `stages/translate/glossary.py` |
| lektor mode | Reading an app in another language in the style of a Polish *lektor*: its lines are translated into the output language and spoken by one voice over the app's own sound, which ducking lowers when it is on. It is on while the input and output languages differ, the translate stage is on and a translation model for the two is installed; without one, the stage does nothing and lines pass untranslated | the `translate` stage (`stages/translate/`), [Translation (lektor mode)](#translation-lektor-mode) |
| translation model | An Argos Translate package for one pair of languages, which the translate stage runs. The interface lists them in the **Translations** tab | `stages/translate/model.py`, `Kind.TRANSLATION` |
| voice | What lines are spoken with: a voice of one speech engine, written `engine:name` | `Voice` and `VoiceInfo` in `tts/engine.py`, `tts/voices.py`, `voice` in the status |
| speech engine | A plugin that turns text into speech with its voices: Piper, Windows | `TtsEngine` and `EnginePlugin` in `tts/engine.py`, `tts/engines/` |
| TTS service | The child process that speaks lines with the current voice, so the core never loads a speech model. The process it runs in is the TTS process. Messages to the user call it speech: "Speech stopped working (exit code 1): see the log." | `tts/` (`service.py`, and `process.py`, its entry point), `TtsClient` in `sinks/tts/client.py` |
| narrator | The core's voice: speaks lines through the TTS service, pauses, stops and switches voices | `Narrator` in `sinks/tts/narrator.py` |
| voice preview | A sample sentence spoken with a voice, through a TTS service of its own. The interface's button is **Preview** | `sinks/tts/preview.py`, `/v1/voices/preview`, `SAMPLES` in `languages.py` |
| speech rate | How fast lines are spoken, as a multiple of the voice's own pace. The interface says **Reading speed** | `speech_rate` in the profile settings and the status, `rate` in `TtsEngine.synthesize` |
| ducking | Lowering the app's sound while the narrator speaks, and bringing it back afterwards. The interface says **Lower app sound while speaking**; the slider is **App volume** | `ducking/`, `Ducker`, `ducking` and `duck_volume` in the status |
| download | A voice or a translation model the user asks for; nothing is downloaded otherwise | `downloads/`, `Downloads` in `downloads/manager.py`, `Kind` in `downloads/source.py` |
| download source | A plugin that lists, installs and removes one kind of download: Piper's voices, Argos Translate's models | `DownloadSource` in `downloads/source.py`, `downloads/piper.py`, `downloads/argos.py` |
| integration | A change in an app's own settings that a source needs before it can read anything, such as VLC's web interface switched on: offered by the source plugin, made when the user enables it and put back when they disable it. A profile whose sources all need one that is off shows as **Not set up** | `Integration` in `integrations.py`, `/v1/integrations`, `desktop/tabs/integration_window.py` |
| the core | The headless part of ReflektorTTS: it finds apps, reads and processes their lines, and serves the local API | `core/`, `Core` in `core/coordinator.py` |
| local API | The versioned HTTP and WebSocket API the core serves on 127.0.0.1, which every user interface uses ([api.md](api.md)) | `api/`, `/v1`, `native/shared/api_client.cpp` |
| event bus | Carries the core's events (lines, subtitles, errors, the status) to whoever listens | `EventBus` in `bus.py`, `events.py` |
| status | What the core is doing now: the app being read, its settings, the voice and a failing source's error. The desktop app shows it in its **Status** tab | `Status` in `events.py`, `/v1/status`, `desktop/tabs/status.py` |
| desktop app | How ReflektorTTS is run: a window and a tray icon that follow the core through the local API, in the process that runs the core | `desktop/` (`Application`, `Window`, `Tray`), `reflektortts.exe` |
| ReflektorTTS window | The desktop app's window, with its Status, Profiles, Voices, Translations and Settings tabs, which the tray icon opens | `Window` in `desktop/window.py`, `root.title("ReflektorTTS")` |
| overlay | The C++ DLL loaded into an app's process, which draws the settings panel and the subtitles on the app's frames | `native/overlay/`, `overlay/`, `overlay` in a profile, `reflektortts-overlay.dll` |
| injector | The program that loads the overlay into a running app | `native/overlay/injector/`, `reflektortts-inject.exe` |
| settings panel | The ImGui panel with an app's settings, in Input, Processing and Output boxes, which the overlay draws over the app and the settings window draws in a window of its own. In the overlay it is "the panel" | `native/shared/settings_panel.cpp`, `native/overlay/src/input/panel_input.cpp` |
| settings window | The settings panel for one profile in a window of its own, which the desktop app opens with **App settings…** | `native/panel/`, `reflektortts-panel.exe`, `desktop/panel/` |

## Processes

```
 App process                        ReflektorTTS process (Python)                   Child process
                                  ┌─────────────────────────────────────────┐
                                  │ Window and tray icon (desktop app)      │
                                  │        │ commands      ▲ status         │
┌───────────────────┐  API /v1    │        ▼               │                │
│ Overlay (C++ DLL) │◄──────────► │ API server (HTTP + WebSocket)           │
│ draws the panel,  │ 127.0.0.1   │        ▲ commands      │ events         │
│ captures input    │ its port    │ Core: profiles, app detection,          │
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
| Settings window (`reflektortts-panel`) | a process of its own, started by the desktop app for one profile | it draws the settings panel (C++), outside any app; it talks to the core through the API, like the overlay |
| Core: profiles, detection, pipeline, API | the ReflektorTTS process, on threads of its own | many small events; calls between processes would only add overhead |
| TTS service | a child process of the core | speech models are heavy and can fail; the core never loads them |

Each ReflektorTTS's API has a port of its own (`identity.py`): 47821 for an installed ReflektorTTS, 47822 for a run from source and 47823 for the end-to-end test's run, so they run side by side. The core gives its port to the overlay, through the injector, when it loads it into an app, and the desktop app gives the same port to the settings windows, as an argument, when it opens them; started by hand without one, they connect to 47821.

## How a line is read

1. The core watches running processes. When one matches an executable in a profile's `match` (by name, and by SHA-256 where the profile lists builds), it loads the overlay into the app if the profile asks for it (and an overlay build was given), and creates the profile's sources through their plugins. A build the profile does not list is neither read nor given the overlay; the status reports it. A profile whose sources all need an **integration** (a change in the app's own settings, such as VLC's web interface switched on, offered by the source plugin) that is not enabled is not watched for at all: the Profiles tab shows it as not set up, and its Integration… button opens a window that enables the integration.
2. The runner polls each source on its interval. A source returns the text currently shown, or nothing.
3. Each reading carries the user's **input language** and **output language**. The text passes through that source's stages, e.g. the **tracker**, which passes a line on once it has settled and only once; **replace**, which removes formatting marks; **translate**, which translates the line into the output language when it differs from the input language; **pronounce**, which respells names from the profile's glossary so the voice says them right ("Carl" as "Karl" in Polish); and **normalize**, which spells out numbers, money and percentages in the output language. Each reading passes through the stages twice, in the same order: once for the **text** shown and once for **speech**, each with its own stage objects, so a stage can be on for one and off for the other. The profile says where each stage starts on (`normalize`, for example, only for speech, so subtitles keep the app's own numbers), and the user can switch it on or off for each in the settings panel; sources the user switched off are not read.
4. Finished lines go to their output's sinks: the speech result to the **TTS sink**, which sends the line to the TTS service at the chosen speed, which, as the user chose, queues it after the line being spoken (the default; at most 3 lines wait, the oldest dropped first), queues it and speeds up the waiting lines to catch up, or cuts the line being spoken off; the text result to the **subtitles sink**, which, when subtitles are on, publishes it as the subtitle to show and later hides it, after the line has been spoken and read, and to the **events sink**, which publishes it to the event bus, from which the API sends lines and subtitles to the overlay, which draws subtitles over the app.
5. The TTS service tells the core when it starts speaking and when it falls silent, and the core's **ducker** lowers the app's sound for that time, lektor style: it fades the app's own audio sessions down (to 30% by default) and back up half a second after the voice stops, so the app does not pump between close lines. Windows keeps each app's mixer volume between runs, so while an app is lowered its original volume is also kept in a file, and a later run puts it back if this one stopped first.
6. When the app exits, the core closes its sources and waits for the next app.

A failing source, stage or sink is reported once as a `source.error`, `stage.error` or `sink.error` event and never stops the rest. The status carries the error of a failing source, as its message changes, until it works again, so the ReflektorTTS window's Status tab, which shows it under what ReflektorTTS is doing, and the settings panel can say what to do also for an app without the overlay.

## Code map

| Path | Job |
|---|---|
| `src/reflektortts/desktop/` | The desktop app, how ReflektorTTS is run (`reflektortts.exe` in a release): runs the core on a background thread, with a tray icon (pystray) and a window (Tkinter) that follow the core through the local API, like the overlay. The window (`window.py`) has a Status tab (`tabs/status.py`: what ReflektorTTS is doing, with an App settings… button for the app being read, its version and links to the project and its support pages, `about.py`), a Profiles tab (with each profile's rating medal, drawn by `tabs/medals.py`, and whose Integration… button opens a window with a group for each integration the selected profile needs, `tabs/integration_window.py`), one tab per kind of download (voices, translations), a Settings tab and a status bar that says what the button under the mouse does. Its subfolders: `api/`, the client of the local API and what it reads from the core's answers; `tabs/`, the tabs; `widgets/`, the parts they share (colors, fonts, tables, the status bar); `panel/`, which opens the settings window for a profile from either tab's App settings… (`launcher.py`): one window per profile, docked beside the ReflektorTTS window (`dock.py`, measured through `win32_windows.py` on Windows), brought to the front when asked for again, and closed when ReflektorTTS quits; and `system/`, where `autostart.py` starts ReflektorTTS, hidden (`--hidden`), when the user signs in to Windows, `session.py` quits when the user signs out of Windows and tells the installer it runs, `tray_host.py` tells whether the desktop has a tray for the icon (without one, as on plain GNOME, closing the window quits ReflektorTTS instead of hiding it), and `state.py` remembers what the app has told the user (`desktop.json`) |
| `core/` | The core. `coordinator.py` holds its state (the app being read, its settings, the narrator and the event bus) and the changes to it, which API requests, the core thread and finished downloads make one at a time, under one lock, so each change is made in full; `watching.py` watches for the apps of the profiles in use and reads each that starts; `reading.py` creates an app's sources and stages and runs them until it exits; `profile_settings.py` turns a profile's settings into what the API shows, and switches its sources and stages; `profile_states.py` says which profiles are used and what each is doing; `integration_control.py` creates the integrations and checks their states; and `source_errors.py` keeps the errors of the failing sources the status shows |
| `__main__.py` | Runs the core in a console, without the window, so developers see the log as it happens |
| `arguments.py`, `logs.py` | Command line options and where logs go, shared by the desktop app and the console |
| `events.py`, `bus.py` | Event types and the event bus |
| `entry_points.py` | Finds plugins through their Python entry points |
| `glossary.py` | A profile's glossary: its terms, and finding them in a line |
| `integrations.py` | The contract of integrations: changes a source plugin makes in the app's own settings, when the user asks, so it can read the app. Each keeps what it changed in `integrations/<type>.json` in the state folder, to put it back |
| `staging.py` | Staging folders, where downloads are put together before they replace what is installed |
| `pipeline/` | Plugin contracts, the plugin registry and the runner |
| `profiles/` | Profiles: the format (`profile.schema.json`), loading, checking and migrating a file (`loader.py`), which profiles are used, of the bundled ones and the user's own (`catalog.py`), the errors of a profile or a part of it that is not there (`errors.py`), and the bundled profiles (`bundled/`); see [profiles.md](profiles.md) |
| `apps/` | Finds running apps with a profile, and which build each is (`executable.py`) |
| `sources/`, `stages/`, `sinks/` | Built-in plugins. `sources/vlc/` also brings the VLC integration, which turns on VLC's web interface in VLC's own settings file |
| `sinks/tts/` | The tts sink: the core's side of speech (the narrator, which pauses and switches voices, and the client that starts the TTS process; the process runs only while an app is read), and the voice preview, which speaks a sample sentence through a TTS process of its own that exits once it is spoken |
| `tts/` | The TTS service process: its entry point (`process.py`, which imports little, so its log is set up before the engines load), the service, speech engines, playback and voices |
| `downloads/` | Downloads the user asks for: the contract download sources follow, the Piper and Argos sources, and the manager running downloads |
| `process_memory/` | Reading a running app's memory for the sources that need it: the process (one implementation per OS, `windows.py`) and pointer chains |
| `ducking/` | Lowers the app's sound while lines are spoken; the per-app volume has one implementation per OS (`windows.py`, WASAPI audio sessions) |
| `languages.py` | The languages: every ISO 639-1 language, read from `languages.json` (generated by `tools/languages.py` from Unicode CLDR, with each language's own and English name, ISO 639-2 codes, Windows code page and whether it separates words), the codes catalogs use for them (`no` for `nb`: Norwegian is listed once, as Bokmål), their checks and the sentences voice previews speak |
| `letters.py` | Letters and words in any script, counting the vowel signs and other marks that scripts such as Hindi's write as characters of their own (Python's `\w` leaves them out) |
| `api/` | The local API: its server thread (`server.py`), the routes and their handlers (`routes.py`), what they need from the core (`control.py`, the `CoreControl` protocol), the JSON they answer with (`encoders.py`), how they read and check request bodies (`bodies.py`), the check that keeps web pages out (`guard.py`) and the error answers (`errors.py`) |
| `settings.py` | Per-user settings: one file per app, and shared ones (the voice remembered for each language, the profiles disabled) |
| `identity.py` | Which ReflektorTTS this is: the installed one, a run from source (ReflektorTTS Dev) or the end-to-end test's (ReflektorTTS E2E), whose name names the per-user folders, the installer's mutexes and the autostart entry; a release is always the installed one |
| `user_dirs.py` | The per-user folders, named after `identity.py`'s name (`%LOCALAPPDATA%\ReflektorTTS` on Windows, with lowercase `logs` and `cache` inside it; platformdirs' folders on Linux) |
| `overlay/` | Loads the overlay into an app; one implementation per OS (`windows.py`, which runs the injector) |
| `native/` (repository root) | The C++ code, in three parts: `shared/`, a library with the API client and the settings panel's drawing; `overlay/`, the overlay DLL loaded into apps, and its injector; and `panel/`, the settings window: the same settings panel for one profile, in a window of its own (SDL3), started by the desktop app as `reflektortts-panel --profile <id>` with `--dock-*` arguments that open it beside the ReflektorTTS window, for apps running or not and apps without the overlay. `CMakeLists.txt` builds them, and `CMakePresets.json` names the builds: `release` (64-bit), `release-x86` (32-bit), `debug`, and `ci`, which the C++ checks read. See [native/README.md](../native/README.md) |
| `.clang-format`, `.clang-tidy` (repository root) | How the C++ code in `native/` is formatted, and what clang-tidy checks in it; each check left out says why |
| `tests/` (repository root) | Tests, mirroring `src/reflektortts/`; `tests/tools/` tests the developer tools, and `tests/e2e/` holds the end-to-end smoke test of the desktop app, which the usual test run leaves out (see [development.md](development.md#end-to-end-tests)) |
| `tools/` (repository root) | Developer tools, not part of ReflektorTTS: `draw_icon.py` draws the ReflektorTTS icon, `languages.py` generates the language table, `build_release.py` builds a release (the installer, from `installer.iss`, and the zip to run without installing), `notices.py` collects the licenses it ships, `sources.py` the source code it offers, `licenses.py` checks that everything a release ships is under a license on its allow list, or one of its exceptions, and `check_includes.py` checks the include directions in `native/` (see [Import directions](#import-directions)) |
| `pyproject.toml` (repository root) | The package: its dependencies and extras, the plugins' entry points, and the settings of Ruff, mypy, pytest and import-linter, whose contracts are the import directions below |
| `docs/` (repository root) | The developer docs: this design, [development.md](development.md) (setup, running from source, every check, the end-to-end tests and the branches), [releasing.md](releasing.md) (how a release is built and published), [interface-texts.md](interface-texts.md) (how the interface's texts are written), [plugins.md](plugins.md), [api.md](api.md) and [profiles.md](profiles.md); and `images/`, the README's icon and screenshots |
| `.github/` (repository root) | The workflows: `checks.yml` (the `Checks`: Lint, the Python checks on Windows and Linux, Licenses and the C++ checks), `e2e.yml` (the end-to-end test), `build-windows.yml` (the Windows release files) and `release.yml` (a release from a tag). `actions/` holds the steps they share: `python/` sets up Python, `linux-libraries/` installs the libraries the Linux jobs need, and `msys2/` sets up MSYS2 for the native code. Also Dependabot's settings, the issue forms and the support links |

How the folders are organized:

- **Plugin folders** (`sources/`, `stages/`, `sinks/`) hold one plugin each. A plugin is a single module while it is small (`stages/tracker.py`) and becomes a package when it needs several files (`stages/normalize/`, `sources/memory/`, `sinks/tts/`). A plugin with rules for each language keeps them in a `languages/` folder, one module per language named after it (`stages/normalize/languages/polish.py`), so adding a language means adding a file, without changing the plugin's mechanism; the plugin maps language codes to them in one place. Likewise, a plugin that reads several file formats keeps one module per format in a `formats/` folder, whose `__init__.py` picks the module by the file's extension (`sources/vlc/formats/srt.py`).
- **Subsystems** that are not plugins sit at the top level: `pipeline/`, `profiles/`, `apps/`, `api/`, `tts/`, `ducking/`, `overlay/`, `desktop/`, and `process_memory/`, which several sources share.
- **A folder that grows past about a dozen modules is split into subfolders by role**, each answering one question, with imports running one way between them: `desktop/` has `api/` (what the core says), `tabs/` (what the window shows), `widgets/` (what the tabs are built from), `panel/` (how the settings window opens) and `system/` (how the app fits into the user's system), with the app itself at its top. The overlay's C++ (`native/overlay/src/`) is split the same way, into `diagnostics/`, `hooks/`, `input/`, `ui/` and `renderers/`. [Import directions](#import-directions) says which way each may import. A module is renamed when its folder makes part of its name redundant (`desktop/tabs/profiles.py`, not `profiles_tab.py`), as long as the shorter name still says on its own what the module is and is not a system header's: the overlay keeps `hooks/code_hook.h` and `input/panel_input.h`, since `code.h` and `panel.h` would say little, and `hooks/d3d9_hook.h`, since `d3d9.h` is Direct3D's. Tests mirror the subfolders.
- **Code for a separate process gets its own folder**, so the layout shows what runs where: `tts/` holds the TTS process, and its client in the core lives with the sink in `sinks/tts/`. The core uses from `tts/` only what it shares with the process: the entry point it starts the process with (`process.py`), the contracts and messages (`engine.py`, `service.py`) and the voice listing (`voices.py`, and `available_voices`, which asks each engine plugin for its voices); it never loads a voice.

Writing plugins: [plugins.md](plugins.md). The local API: [api.md](api.md).

## Import directions

Imports run one way between folders, and two checks of the `Checks` workflow fail when one runs the other way. [development.md](development.md#checks) says how to run them.

**Python.** The contracts in `[tool.importlinter]` in `pyproject.toml`, each named after its rule, write these directions down, and [import-linter](https://import-linter.readthedocs.io/) checks them (`lint-imports`, in the `Lint` job). Paths are in `src/reflektortts/`:

1. **Nothing outside `desktop/` imports the desktop app**: the core runs headless.
2. **The desktop app imports none of the core's parts**: it follows the core through the local API. It may import only what it shares with the core: `api/` (the API's address and errors), `arguments.py`, `identity.py`, `logs.py`, `user_dirs.py`, `settings.py`, `languages.py` and `downloads/source.py` (the kinds of download). It imports none of `apps/`, `bus.py`, `core/`, `downloads/`'s other modules, `ducking/`, `entry_points.py`, `events.py`, `glossary.py`, `integrations.py`, `letters.py`, `overlay/`, `pipeline/`, `process_memory/`, `profiles/`, `sinks/`, `sources/`, `staging.py`, `stages/` or `tts/`. The one exception is `desktop/core_thread.py`, which imports `core/coordinator.py` to start the core and stop it. The rest of the core comes in through it, and through `api/server.py`, where the API's address and errors are, so only the desktop app's own imports are checked.
3. **Inside `desktop/`, imports run from the app at the top down to what it is built from**: `__main__.py`, then `application.py`, then `window.py` and `tray.py`, then `tabs/`, then `api/`, `widgets/`, `panel/` and `system/`. Each imports only from those below it, and those on one level (`window.py` and `tray.py`; `api/`, `widgets/`, `panel/` and `system/`) not from each other. The modules beside them (`about.py`, `core_thread.py`, `icon.py`) are not in this order.
4. **Inside `core/`, imports run from the core's state at the top down to the parts it is built from**: `coordinator.py`, then `watching.py`, `profile_states.py` and `profile_settings.py`, then `reading.py`, `integration_control.py` and `source_errors.py`. Each imports only from those below it, and those on one level not from each other.
5. **Nothing imports a plugin, and no plugin imports another**: plugins are found through their entry points. This covers each plugin in `sources/`, `stages/` and `tts/engines/`, and the download sources `downloads/argos.py` and `downloads/piper.py`; a plugin's own modules import each other freely. The exceptions are the download sources, which install what they download where its stage or engine finds it ([plugins.md](plugins.md)): `downloads/argos.py` imports `stages/translate/model.py`, and `downloads/piper.py` imports `tts/engines/piper.py`.
6. **Plugins use the core only through the plugin contracts**: no plugin imports `api/`, `bus.py`, `core/`, `desktop/`, `downloads/manager.py`, `ducking/`, `overlay/`, `pipeline/runner.py`, `profiles/catalog.py` or `sinks/`. Only a plugin's own imports are checked, not what the shared modules it imports import in turn.
7. **Only `tts/` imports the speech engines (`tts/engines/`) and the player (`tts/playback.py`)**: the core uses only what `tts/` shares with it (see above), and never loads a voice. The exception is `downloads/piper.py`, as in 5.
8. **Only the platform modules import the system's own libraries**: comtypes, pycaw and winrt (Windows) and python-xlib (Linux) are imported only by `desktop/system/tray_host.py`, `ducking/windows.py` and `tts/engines/windows.py`.

An import a contract must allow goes into the contract's `ignore_imports`, with a comment saying why.

**C++.** `tools/check_includes.py` checks the includes of `native/` (in the `C++ checks` job), in the directions [native/README.md](../native/README.md) writes down:

1. **`shared/` includes nothing from `overlay/` or `panel/`, and `panel/` nothing from `overlay/`.** The overlay and the settings window both build on the shared library.
2. **The overlay's own headers are included by their path from `native/overlay/src/`** (`"hooks/code_hook.h"`).
3. **In `native/overlay/src/`, each folder includes only from itself and the folders listed before it**, in the order `diagnostics/`, `hooks/`, `input/`, `ui/`, `renderers/`. `dllmain.cpp`, at the top, ties them together, and no folder includes from it.
4. **A header in quotes is one of the project's own**; system and library headers are included with `<>`.

A new folder in `native/overlay/src/` goes into `OVERLAY_FOLDERS` in `tools/check_includes.py`, at its place in the order, and into native/README.md.

## Text sources

| Source | Works without subtitles | Coverage | State |
|---|---|---|---|
| Memory: subtitle buffer (`memory`) | no | per app | Works: GTA2, GTA III, GTA Vice City, GTA San Andreas. Needs a static pointer to the text |
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
- **Languages:** any pair Argos Translate has a model for can be downloaded and used: English to and from about 50 languages, and Spanish to and from Portuguese. Voices come from Piper, or Windows. Every ISO 639-1 language can be chosen as the input or output language, so a new model or voice in the catalogs works without changes here; what a language has besides (normalization, name endings, a voice preview sentence) comes from plugins' rules for it. The splitter knows the sentence endings of Chinese, Japanese, Arabic, Urdu, Hindi, Armenian, Ethiopic, Burmese, Tibetan and Khmer, and lines in Chinese and Japanese are joined without spaces. In languages written without spaces between words (Chinese, Japanese, Thai…), glossary terms are found anywhere in a line. Known limits: the overlay's font (Segoe UI) has Latin, Greek, Cyrillic, Armenian, Georgian, Arabic and Hebrew letters only, so other scripts (Chinese, Japanese, Korean, Thai, Indic, Ethiopic, Khmer, Burmese and more) show as boxes, and right-to-left text (Arabic, Hebrew, Persian, Urdu…) shows reversed; and the glossary's stand-ins are English names, which a model writing another script spells its own way ("Кевин"), so a kept term is put back only in output written in Latin letters.
- **Engine:** Argos Translate's models (most OPUS-MT based, CC-BY 4.0; English–Polish is the one compared below), run directly with CTranslate2 on the CPU (in the type the model was saved in, int8 for most) and tokenized as it was trained (Moses tokens split into BPE subwords, or SentencePiece pieces, whichever tokenizer the package comes with), without the `argostranslate` package and its heavy dependencies. It runs in the core process, at about 0.1 s per line and at most 0.4 s, once per settled line. The model is loaded once and shared by every translate stage, of every source and app. Only an installed model is used, never downloaded by the stage (downloads belong in the desktop app).
- **Why this engine:** an EN→PL benchmark on game lines compared it with Opus-MT `en-zlw` and `tc-bible-big`, Firefox Translations' model (through `fxtranslate`), and Meta's NLLB-200 600M and M2M-100 418M. It gave the most natural translations and was the fastest. Firefox's model needs a Marian-based engine (its SSRU decoder does not run on CTranslate2), and NLLB-200 is licensed for non-commercial use only.
- **Normalization** (the `normalize` stage) covers, in English and Polish: numbers, money, percentages, units after numbers (km, m, kg, min, s, °C…; one-letter units only after a space, so "the 80s" stays a decade), times of day (Polish hours after "o", "do", "przed"… take their case: "o czternastej"), dates with a year ("12.05.2024", "2024-05-12"; without a year "1.5." would be taken for the first of May), common abbreviations and the symbols & and +. In Polish, 1 and 2 take the gender of a following noun common in games ("dwie minuty", "jedną szansę").
- **Planned:** translating between two languages through English, for pairs without a model; fallback fonts and right-to-left text in the overlay; online engines (e.g. DeepL, LLMs) as plugins that can use an app's context; for sources with labels, translating the whole text table ahead of time into a label → translation dictionary, with no delay and room for manual corrections; in normalization, other Polish cases (e.g. "po dwóch minutach", "na ulicę" for "na ul.") and timers such as "02:30", which are read as clock times.

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

- **Windows** is the main platform, and for now the only one with a release ([releasing.md](releasing.md)). ReflektorTTS ships as an installer and as a zip of the same files, to unpack and run without installing: the desktop app built with PyInstaller (one folder, its own Python, every dependency included), the settings window, the overlay builds and the notices, built by `tools/build_release.py`, with a zip of the source code it offers next to them. The installer (Inno Setup) installs for the current user, with no administrator rights, or for all users, and asks the user to quit a running ReflektorTTS before an update or removal: `desktop/system/session.py` holds named mutexes it looks for, which every user may see. User data stays in the per-user folders, so updating replaces only the program folder.
- The desktop app uses Tkinter, part of Python, and pystray (LGPL-3.0) for the tray icon; Qt or wx would look more modern but add over 100 MB. The overlay works only with what is already downloaded: downloads (voices, translation models) belong in the desktop app.
- **Linux** second, planned: it has no release yet, but its Python checks and the end-to-end test run in CI, so the code stays portable until the ports land. Apps under Proton/Wine with the same overlay DLL; native apps through a Vulkan layer and `LD_PRELOAD` for OpenGL (as MangoHud does). Sources to port: memory (`process_vm_readv`), which `avalanche` reads through too; OCR (Tesseract) and the clipboard, once they exist. Ducking needs a per-app volume through PipeWire/PulseAudio (e.g. `pulsectl`). The settings window (`native/panel/`, SDL3) is portable, but needs a small loopback HTTP/WebSocket transport there in place of WinHTTP before it can be built. pystray and Tkinter both want the main thread on some Linux setups, so the desktop app is checked there separately.
- **macOS** is out of scope: the hardened runtime and SIP block injection, and reading memory (`task_for_pid`) needs extra permissions.
- The core and its UIs stay portable; platform-specific code lives only in plugins, in platform modules with one implementation per OS behind a small interface (`ducking/windows.py`, `overlay/windows.py`, `process_memory/windows.py`, `desktop/system/tray_host.py`), and in `native/`. Rule 7 of the [import directions](#import-directions) checks that the system's own Python libraries are imported only in such modules.

## Open questions

- How community profiles are distributed beyond this repository (e.g. a profile browser in ReflektorTTS).
- Whether the API needs authentication beyond listening only on 127.0.0.1 and refusing web pages (other programs on the machine can still use it).
