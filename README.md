# ReflektorTTS

Your apps, read aloud. ReflektorTTS speaks the dialogue, subtitles and messages of games and other apps, and translates them into your language on the way, in the style of a Polish *lektor*: one voice over the original sound. It runs offline, from a desktop app next to the clock, and in apps with the overlay everything is set from inside the app, without Alt+Tab.

## Supported apps

Each app is described by a profile. ReflektorTTS comes with profiles for:

- **Grand Theft Auto 2** (the 9.6 freeware release): subtitles, read from the game's memory.
- **Grand Theft Auto: San Andreas** (the Steam release): subtitles and the help box, read from the game's memory, with a glossary that keeps names like Sweet and Big Smoke untranslated and pronounces them right in Polish.
- **Mad Max** (2015, Steam): subtitles, with their text read from the game's files in the input language you choose.

More apps can be added with a profile of your own; see [Profiles](#profiles).

## Download (Windows)

ReflektorTTS comes as a portable zip, `ReflektorTTS-<version>-windows-x64.zip`, from the repository's Releases page; nothing is installed. Unpack it anywhere and run `ReflektorTTS.exe` in the `ReflektorTTS` folder; the `README.txt` there says the rest. Your settings, downloaded voices and models, your own profiles and the logs are kept in `%LOCALAPPDATA%\ReflektorTTS`, so to update, replace the folder with a newer release.

The overlay works by loading into the app, as in-game overlays do, which antivirus programs may distrust. If yours blocks `reflektortts-inject.exe` in the `overlay` folder, allow it to use the overlay; apps are read without it too.

## First run

ReflektorTTS runs next to the clock: its icon there opens the window, pauses reading or quits. Closing the window leaves ReflektorTTS running.

- **Status** shows what ReflektorTTS is doing: the app it reads, or that it waits for one, and an app version its profile does not support. It also opens the logs and settings folders.
- **Profiles** lists the profiles, bundled and your own, says which are used and why others are not, enables or disables them, and copies, removes or imports profile files.
- **Voices** and **Translations** download voices and translation models (see [Voices](#voices) and [Translation](#translation)).

Windows already has voices, so ReflektorTTS speaks without downloading anything. For better voices, or to translate, get them in the Voices and Translations tabs; ReflektorTTS never downloads anything by itself.

Then start an app it has a profile for. ReflektorTTS reads its text aloud, and loads the overlay into it if its profile asks for that; when the app exits, it waits for the next one. An app's voice is loaded when the app starts and unloaded when it closes, so nothing is loaded while ReflektorTTS waits.

## In the app

In an app with the overlay, press **Ctrl+Shift+R** to open the ReflektorTTS panel. From top to bottom it follows a line through ReflektorTTS: the input (its language and the app's sources), the processing stages, each switched on and off for the text shown and for speech, and the output (language, voice, reading speed, what a new line does while another is spoken, app sound, pause, subtitles). It also shows the last line read. See [overlay/README.md](overlay/README.md).

Everything chosen in the panel, the voice included, is saved for each app, in `%LOCALAPPDATA%\ReflektorTTS\settings\profiles\`, one file per app named like its profile (e.g. `mad-max-2015.json`). An app used for the first time starts with the defaults, and deleting its file resets it. `%LOCALAPPDATA%\ReflektorTTS\settings\shared.json` remembers the voice last chosen for each language, so switching an app's output language picks it again.

## Voices

- **Windows** voices installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish). Windows comes with some, so ReflektorTTS can speak without downloading anything.
- **Piper** voices, downloaded in the Voices tab into `%LOCALAPPDATA%\ReflektorTTS\voices`. The preferred default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset; without it, apps use an installed voice for their output language.

The Voices and Translations tabs list what Piper and Argos Translate publish. Select one to read its license as published (for Piper voices, the voice's model card) and to open its page, then **Download** it; it can be used right away, even in an app that is running. **Remove** deletes it again. **Preview** speaks a sentence in an installed voice, also while an app is read. The Voices tab also lists the Windows voices for the languages ReflektorTTS supports; they are added and removed in Windows Settings.

Any output language can be chosen. Without a voice for it, the panel's Voice box says so and lines are only translated and shown as subtitles.

## Translation

ReflektorTTS translates an app into your language, in the style of a Polish *lektor*. Set the input language (in the panel's Input section) and the output language (in Output); when they differ, each line is translated before it is spoken and shown. To hear the original instead, untick `translate` in the panel's Processing section, under Text, Speech or both.

It uses the translation models of [Argos Translate](https://github.com/argosopentech/argos-translate), one per pair of languages, downloaded in the Translations tab into `%LOCALAPPDATA%\ReflektorTTS\translation`. They run offline on the CPU, at about 0.1 s per line. Without a model for the input and output languages, `translate` is grayed out with "No translation model for these languages" and lines are read untranslated. The English–Polish model (about 80 MB), for example, is derived from an [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) model by Jörg Tiedemann and Santhosh Thottingal and licensed CC-BY 4.0.

A profile's glossary helps the translation along: it keeps names that are also words untranslated ("Sweet" stays a name), gives slang its meaning ("hood" is not a car's hood), and says how names are pronounced for the voice ("Carl" is read "Karl" in Polish, while subtitles keep "Carl"). See [docs/profiles.md](docs/profiles.md).

## App sound

While a line is spoken, ReflektorTTS lowers the app's sound, like a *lektor* speaking over the original, and brings it back half a second after the voice stops. By default the app drops to 30% of its own volume; the panel's Output section switches this off or sets the level. Only the app's slider in the Windows volume mixer is changed, not other apps. If ReflektorTTS stops while the app is lowered, the app's own volume is kept in `%LOCALAPPDATA%\ReflektorTTS\lowered-apps.json` and put back the next time the app starts.

## Subtitles

ReflektorTTS can also show each line as a subtitle over the app, for example the Polish translation while the original plays. Switch them on under Subtitles in the panel's Output section, where you also set their size and whether they sit at the top or the bottom of the screen. They are at the top by default, so the app's own text, usually at the bottom, stays visible. A subtitle stays while its line is spoken and a moment after, and at least as long as it takes to read, so subtitles also work with speech paused.

## Profiles

Each app is described by one JSON file, a profile: how to recognize the app, where to read its text, how to process it, and its glossary. ReflektorTTS comes with profiles for the apps above; your own go in `%LOCALAPPDATA%\ReflektorTTS\profiles\`, where one with a bundled profile's name replaces it, and the Profiles tab imports them. [docs/profiles.md](docs/profiles.md) explains where profiles are, how they are chosen, and their format.

## Documentation

- [docs/profiles.md](docs/profiles.md): profiles and their format
- [overlay/README.md](overlay/README.md): the overlay
- [docs/architecture.md](docs/architecture.md): how ReflektorTTS is built, and what is planned
- [docs/plugins.md](docs/plugins.md): writing sources, stages, speech engines and download sources
- [docs/api.md](docs/api.md): the local API, through which the desktop app and the overlay control ReflektorTTS (`http://127.0.0.1:47821/v1`)

## Development

### Setting up from source (Windows)

You need Python 3.13 and, for the overlay, MSYS2 (see [overlay/README.md](overlay/README.md)). From the repository root:

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\pip install -e .[dev]
```

This installs ReflektorTTS with everything it needs, and the `dev` extra adds the tools for tests and checks. Build the overlay as described in [overlay/README.md](overlay/README.md).

### Running from source

The desktop app, as users run it: double-click `start.bat` in the repository root, or run

```bash
.venv\Scripts\reflektortts-desktop --overlay overlay\build\bin --overlay overlay\build64\bin
```

Logs are written to `%LOCALAPPDATA%\ReflektorTTS\Logs`. To see the log while working on the code, run ReflektorTTS without the window, in a console, and stop it with Ctrl+C:

```bash
.venv\Scripts\python -m reflektortts --overlay overlay\build\bin --overlay overlay\build64\bin
```

Both take the same options:

- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the app is used. Without it, apps run without the overlay. A release finds its overlay builds next to `ReflektorTTS.exe` by itself.
- `--profiles DIR`: folder with your own profiles, used next to the bundled ones. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\ReflektorTTS\profiles`).

### Checks

```bash
.venv\Scripts\python -m pytest
```
```bash
.venv\Scripts\python -m ruff check
```
```bash
.venv\Scripts\python -m mypy
```

The icon of ReflektorTTS, `src/reflektortts/desktop/icon.ico`, is drawn in code by `tools/draw_icon.py`; after changing the drawing, run it from the repository root to write the icon again:

```bash
.venv\Scripts\python tools\draw_icon.py
```

### Building a release

`tools/build_release.py` builds two zips into `build\release\`, both uploaded to the release's page on GitHub, under the tag `v<version>`:

- `ReflektorTTS-<version>-windows-x64.zip`: `ReflektorTTS.exe` (the desktop app with its own Python, built with PyInstaller), both overlay builds, `LICENSE.txt`, `COPYRIGHT.txt`, a `README.txt` for users, and `THIRD_PARTY_NOTICES.txt`, generated by `tools/notices.py` from the installed packages' metadata.
- `ReflektorTTS-<version>-sources.zip`: the source code the release offers, as the GPL asks, made by `tools/sources.py`: ReflektorTTS at the commit the release is built from, and the source of every shipped package under the GPL, LGPL or MPL, at the shipped version.

It needs git, the `release` extra and both overlay builds (see [overlay/README.md](overlay/README.md)), and every change committed:

```bash
.venv\Scripts\pip install -e .[release]
```
```bash
.venv\Scripts\python tools\build_release.py
```

A release is refused while a shipped package has no license text, or a shipped package under the GPL, LGPL or MPL has no source listed:

- Add a license text that a package doesn't install, or the notices of parts it contains without them (such as native libraries compiled into it), to `tools/licenses/<package>.txt`, from the project's source at the shipped version.
- Add where a package's source is, for its exact version, to `SOURCES` in `tools/sources.py`.

`--draft` builds anyway, to test, from uncommitted changes too, marking what is missing and the zips' names.

## License

Copyright (C) 2026 Infinitinker. ReflektorTTS is free software under the GPL-3.0-or-later; see [LICENSE](LICENSE). [COPYRIGHT](COPYRIGHT) adds a permission to combine it with the Intel and NVIDIA libraries that CTranslate2, the translation engine, is built with. The overlay includes Dear ImGui, nlohmann/json, MinHook and the MinGW-w64 runtime, whose licenses are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

Reading Avalanche games' files follows the formats as documented by [Gibbed.MadMax](https://github.com/gigaHours/Gibbed.MadMax) (Rick Gibbed, zlib license); file names are hashed with Bob Jenkins' public-domain lookup3. An app's text is read from the user's own copy while it runs and is not stored.
