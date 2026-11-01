# ReflektorTTS

Your game, read aloud. ReflektorTTS reads game text (dialogue, subtitles, on-screen messages) and speaks it, configured per game through profiles and from inside the game through an overlay.

This is an early version for developers: there is no installer yet. It has profiles for Grand Theft Auto 2 (the 9.6 freeware release) and Grand Theft Auto: San Andreas (the Steam release: subtitles and the help box), both read from the game's memory, and Mad Max (2015, Steam: subtitles, with their text read from the game's files in the game language set in the overlay).

## Setting up (Windows)

You need Python 3.13 and, for the in-game overlay, MSYS2 (see [overlay/README.md](overlay/README.md)).

From the repository root:

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\pip install -e .[dev,translate,desktop]
```

The `translate` extra is only needed to translate games (see [Translation](#translation)), and `desktop` only for the desktop app (see [Running](#running)).

Build the overlay as described in [overlay/README.md](overlay/README.md).

## Running

As a desktop app, without a console: double-click `start-app.bat` in the repository root, or run

```bash
.venv\Scripts\reflektortts-app --profiles profiles --overlay overlay\build\bin --overlay overlay\build64\bin
```

Its icon appears next to the clock: right-click it to open the window, pause reading or quit. The window shows what ReflektorTTS is doing and opens its logs and settings folders; closing it leaves ReflektorTTS running. Logs are written to `%LOCALAPPDATA%\ReflektorTTS\Logs`.

Or in a console, with the log shown there:

```bash
.venv\Scripts\python -m reflektortts --profiles profiles --overlay overlay\build\bin --overlay overlay\build64\bin
```

Either way, ReflektorTTS then waits for a game it has a profile for. When you start the game, it loads the overlay into it and reads its text aloud; when the game exits, it waits for the next one. In the console, stop it with Ctrl+C.

- `--profiles DIR`: folder with game profiles. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\ReflektorTTS\profiles`).
- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the game is used. Without it, games run without the overlay.

A game's voice is loaded when the game starts and unloaded when it closes, so nothing is loaded while ReflektorTTS waits. ReflektorTTS never downloads anything by itself: it uses the voices and translation models that are installed (see [Voices](#voices) and [Translation](#translation)).

## In the game

Press **Ctrl+Shift+R** to open the ReflektorTTS panel. From top to bottom it follows a line through the app: the game and its sources, the text processing stages, and the output (language, voice, game sound, pause, subtitles). It also shows the last line read. See [overlay/README.md](overlay/README.md).

## Voices

- **Windows** voices installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish). Windows comes with some, so ReflektorTTS can speak without downloading anything.
- **Piper** voices in `%LOCALAPPDATA%\ReflektorTTS\voices`, used once downloaded. The preferred default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset; without it, games use an installed voice for their output language.

Any output language can be chosen. Without a voice for it, the panel's Voice box says so and lines are only translated and shown as subtitles.

Voices and translation models are downloaded only when you ask for it, from the lists Piper and Argos Translate publish, each shown with its licence as published. The desktop app's section for that comes next; until then, with ReflektorTTS running, the local API lists and downloads them (see [docs/api.md](docs/api.md#downloads)), e.g.:

```bash
curl "http://127.0.0.1:47821/v1/downloads?refresh=1"
```
```bash
curl -X POST http://127.0.0.1:47821/v1/downloads -H "Content-Type: application/json" -d "{\"id\": \"piper:en_US-ljspeech-medium\"}"
```

Everything chosen in the panel, the voice included, is saved for each game, in `%LOCALAPPDATA%\ReflektorTTS\games\`, one file per game named like its profile (e.g. `mad-max-2015.json`). A game played for the first time starts with the defaults, and deleting its file resets it. `%LOCALAPPDATA%\ReflektorTTS\settings.json` remembers the voice last chosen for each language, so switching a game's output language picks it again.

## Game sound

While a line is spoken, ReflektorTTS lowers the game's sound, like a *lektor* speaking over the original, and brings it back half a second after the voice stops. By default the game drops to 30% of its own volume; the panel's Output section switches this off or sets the level. Only the game's slider in the Windows volume mixer is changed, not other apps. If ReflektorTTS stops while the game is lowered, the game's own volume is kept in `%LOCALAPPDATA%\ReflektorTTS\lowered-games.json` and put back the next time the game starts.

## Subtitles

ReflektorTTS can also show each line as a subtitle over the game, for example the Polish translation while the original plays. Switch them on under Subtitles in the panel's Output section, where you also set their size and whether they sit at the top or the bottom of the screen. They are at the top by default, so the game's own text, usually at the bottom, stays visible. A subtitle stays while its line is spoken and a moment after, and at least as long as it takes to read, so subtitles also work with speech paused.

## Translation

ReflektorTTS can translate a game into the output language, in the style of a Polish *lektor*. Set the game language (in the panel's Game section) and the output language (in Output); when they differ, profiles with a `translate` stage translate each line before it is spoken. To turn it off, untick `translate` in the panel's Text processing section.

Only English to Polish is available so far. It runs offline on the CPU, at about 0.1 s per line, with the model (about 80 MB) in `%LOCALAPPDATA%\ReflektorTTS\translation`. Without it, `translate` is greyed out with "No translation model for these languages" and lines are read untranslated. Download it like a voice, with the ID `argos:en-pl`.
 It is the English–Polish model of [Argos Translate](https://github.com/argosopentech/argos-translate), derived from an [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) model by Jörg Tiedemann and Santhosh Thottingal and licensed CC-BY 4.0.

## Local API

Every UI talks to the core through the same local API on `http://127.0.0.1:47821/v1`: status, voices, settings, pause/resume, and a WebSocket of events. See [docs/api.md](docs/api.md).

## Game profiles

Each game is described by one JSON file in [profiles/](profiles/README.md), which explains the format.

## Documentation

- [docs/architecture.md](docs/architecture.md): how ReflektorTTS is built, and what is planned
- [docs/plugins.md](docs/plugins.md): writing sources, stages and speech engines
- [docs/api.md](docs/api.md): the local API
- [profiles/README.md](profiles/README.md): writing game profiles
- [overlay/README.md](overlay/README.md): the in-game overlay

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

The app's icon, `src/reflektortts/desktop/icon.ico`, is drawn in code by `tools/draw_icon.py`; after changing the drawing, run it from the repository root to write the icon again:

```bash
.venv\Scripts\python tools\draw_icon.py
```

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).

Reading Avalanche games' files follows the formats as documented by [Gibbed.MadMax](https://github.com/gigaHours/Gibbed.MadMax) (Rick Gibbed, zlib licence); file names are hashed with Bob Jenkins' public-domain lookup3. A game's text is read from the player's own copy while it runs and is not stored.
