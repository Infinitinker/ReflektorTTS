# ReflektorTTS

Your apps, read aloud. ReflektorTTS reads the text an app shows (dialogue, subtitles, on-screen messages) and speaks it, and can translate it into your language on the way, in the style of a Polish *lektor*: one voice over the original. Each app is described by a profile, and apps with the overlay are configured from inside them.

This is an early version. It has profiles for Grand Theft Auto 2 (the 9.6 freeware release) and Grand Theft Auto: San Andreas (the Steam release: subtitles and the help box), both read from the app's memory, and Mad Max (2015, Steam: subtitles, with their text read from the app's files in the input language set in the overlay).

## Download (Windows)

ReflektorTTS comes as a portable zip, `ReflektorTTS-<version>-windows-x64.zip`, from the repository's Releases page; nothing is installed. Unpack it anywhere and run `ReflektorTTS.exe` in the `ReflektorTTS` folder; the `README.txt` there says the rest. Your settings, downloaded voices and models, your own profiles and the logs are kept in `%LOCALAPPDATA%\ReflektorTTS`, so to update, replace the folder with a newer release.

The overlay works by loading into the app, as in-game overlays do, which antivirus programs may distrust. If yours blocks `reflektortts-inject.exe` in the `overlay` folder, allow it to use the overlay; apps are read without it too.

## Setting up from source (Windows)

You need Python 3.13 and, for the overlay, MSYS2 (see [overlay/README.md](overlay/README.md)).

From the repository root:

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\pip install -e .[dev,translate,desktop]
```

The `translate` extra is only needed to translate (see [Translation](#translation)), and `desktop` only for the desktop app (see [Running](#running)).

Build the overlay as described in [overlay/README.md](overlay/README.md).

## Running

As a desktop app, without a console: double-click `start.bat` in the repository root, or run

```bash
.venv\Scripts\reflektortts-desktop --overlay overlay\build\bin --overlay overlay\build64\bin
```

Its icon appears next to the clock: right-click it to open the window, pause reading or quit. The window's Status tab shows what ReflektorTTS is doing and opens its logs and settings folders; its Profiles tab lists the profiles, bundled and your own, says which are used and why others are not, enables or disables them, and copies, removes or imports profile files; its Voices and Translations tabs download voices and translation models. Closing it leaves ReflektorTTS running. Logs are written to `%LOCALAPPDATA%\ReflektorTTS\Logs`.

Or in a console, with the log shown there:

```bash
.venv\Scripts\python -m reflektortts --overlay overlay\build\bin --overlay overlay\build64\bin
```

Either way, ReflektorTTS then waits for an app it has a profile for. When you start the app, it reads its text aloud, and loads the overlay into it if its profile asks for that; when the app exits, it waits for the next one. A version of the app its profile does not list is not read, and the Status tab says so. In the console, stop it with Ctrl+C.

- `--profiles DIR`: folder with your own profiles, used next to the bundled ones. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\ReflektorTTS\profiles`).
- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the app is used. Without it, apps run without the overlay.

An app's voice is loaded when the app starts and unloaded when it closes, so nothing is loaded while ReflektorTTS waits. ReflektorTTS never downloads anything by itself: it uses the voices and translation models that are installed (see [Voices](#voices) and [Translation](#translation)).

## In the app

In an app with the overlay, press **Ctrl+Shift+R** to open the ReflektorTTS panel. From top to bottom it follows a line through ReflektorTTS: the input (its language and the app's sources), the processing stages, each switched on and off for the text shown and for speech, and the output (language, voice, app sound, pause, subtitles). It also shows the last line read. See [overlay/README.md](overlay/README.md).

## Voices

- **Windows** voices installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish). Windows comes with some, so ReflektorTTS can speak without downloading anything.
- **Piper** voices in `%LOCALAPPDATA%\ReflektorTTS\voices`, used once downloaded. The preferred default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset; without it, apps use an installed voice for their output language.

Any output language can be chosen. Without a voice for it, the panel's Voice box says so and lines are only translated and shown as subtitles.

Voices and translation models are downloaded only when you ask for it: in the desktop app's **Voices** and **Translations** tabs, which list what Piper and Argos Translate publish. Select one to read its license as published (for Piper voices, the voice's model card) and to open its page, then **Download** it; it can be used right away, even in an app that is running. **Remove** deletes it again. **Preview** speaks a sentence in an installed voice, also while an app is read. The Voices tab also lists the Windows voices for the languages ReflektorTTS supports; they are added and removed in Windows Settings.

Everything chosen in the panel, the voice included, is saved for each app, in `%LOCALAPPDATA%\ReflektorTTS\settings\profiles\`, one file per app named like its profile (e.g. `mad-max-2015.json`). An app used for the first time starts with the defaults, and deleting its file resets it. `%LOCALAPPDATA%\ReflektorTTS\settings\shared.json` remembers the voice last chosen for each language, so switching an app's output language picks it again.

## App sound

While a line is spoken, ReflektorTTS lowers the app's sound, like a *lektor* speaking over the original, and brings it back half a second after the voice stops. By default the app drops to 30% of its own volume; the panel's Output section switches this off or sets the level. Only the app's slider in the Windows volume mixer is changed, not other apps. If ReflektorTTS stops while the app is lowered, the app's own volume is kept in `%LOCALAPPDATA%\ReflektorTTS\lowered-apps.json` and put back the next time the app starts.

## Subtitles

ReflektorTTS can also show each line as a subtitle over the app, for example the Polish translation while the original plays. Switch them on under Subtitles in the panel's Output section, where you also set their size and whether they sit at the top or the bottom of the screen. They are at the top by default, so the app's own text, usually at the bottom, stays visible. A subtitle stays while its line is spoken and a moment after, and at least as long as it takes to read, so subtitles also work with speech paused.

## Translation

ReflektorTTS can translate an app into the output language, in the style of a Polish *lektor*. Set the input language (in the panel's Input section) and the output language (in Output); when they differ, profiles with a `translate` stage translate each line before it is spoken. To turn it off, untick `translate` in the panel's Processing section, under Text, Speech or both.

It uses the translation models of [Argos Translate](https://github.com/argosopentech/argos-translate), one per pair of languages, downloaded in the desktop app's Translations tab into `%LOCALAPPDATA%\ReflektorTTS\translation`. They run offline on the CPU, at about 0.1 s per line. Without a model for the input and output languages, `translate` is grayed out with "No translation model for these languages" and lines are read untranslated. The English–Polish model (about 80 MB), for example, is derived from an [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) model by Jörg Tiedemann and Santhosh Thottingal and licensed CC-BY 4.0.

## Local API

Every UI talks to the core through the same local API on `http://127.0.0.1:47821/v1`: status, voices, settings, pause/resume, and a WebSocket of events. See [docs/api.md](docs/api.md).

## Profiles

Each app is described by one JSON file, a profile. ReflektorTTS comes with profiles for the apps above; your own go in `%LOCALAPPDATA%\ReflektorTTS\profiles\`, where one with a bundled profile's name replaces it. [docs/profiles.md](docs/profiles.md) explains where profiles are, how they are chosen, and their format.

## Documentation

- [docs/architecture.md](docs/architecture.md): how ReflektorTTS is built, and what is planned
- [docs/plugins.md](docs/plugins.md): writing sources, stages and speech engines
- [docs/api.md](docs/api.md): the local API
- [docs/profiles.md](docs/profiles.md): profiles and their format
- [overlay/README.md](overlay/README.md): the overlay

## Development

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

`tools/build_release.py` builds the portable zip into `build\release\`: `ReflektorTTS.exe` (the desktop app with its own Python, built with PyInstaller), both overlay builds, `LICENSE.txt`, a `README.txt` for users, and `THIRD_PARTY_NOTICES.txt`, generated by `tools/notices.py` from the installed packages' metadata. It needs the `release` extra and both overlay builds (see [overlay/README.md](overlay/README.md)):

```bash
.venv\Scripts\pip install -e .[desktop,translate,release]
```
```bash
.venv\Scripts\python tools\build_release.py
```

A release is refused until the source address in `pyproject.toml` (`[project.urls]`) is set, and while a shipped package has no license text: add one that installs none to `tools/licenses/<package>.txt`, from the project's source at the shipped version. `--draft` builds anyway, to test, marking what is missing and the zip's name.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE). The overlay includes Dear ImGui, nlohmann/json and MinHook, whose licenses are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

Reading Avalanche games' files follows the formats as documented by [Gibbed.MadMax](https://github.com/gigaHours/Gibbed.MadMax) (Rick Gibbed, zlib license); file names are hashed with Bob Jenkins' public-domain lookup3. An app's text is read from the user's own copy while it runs and is not stored.
