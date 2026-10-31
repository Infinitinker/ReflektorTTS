# ReflektorTTS

Your game, read aloud. ReflektorTTS reads game text (dialogue, subtitles, on-screen messages) and speaks it, configured per game through profiles and from inside the game through an overlay.

This is an early version for developers: there is no installer yet. It has profiles for Grand Theft Auto 2 (the 9.6 freeware release) and Grand Theft Auto: San Andreas (the Steam release: subtitles and the help box), both read from the game's memory.

## Setting up (Windows)

You need Python 3.13 and, for the in-game overlay, MSYS2 (see [overlay/README.md](overlay/README.md)).

From the repository root:

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\pip install -e .[dev,translate]
```

The `translate` extra is only needed to translate games (see [Translation](#translation)).

Build the overlay as described in [overlay/README.md](overlay/README.md).

## Running

```bash
.venv\Scripts\python -m reflektortts --profiles profiles --overlay overlay\build\bin --overlay overlay\build64\bin
```

ReflektorTTS then waits for a game it has a profile for. When you start the game, it loads the overlay into it and reads its text aloud; when the game exits, it waits for the next one. Stop it with Ctrl+C.

- `--profiles DIR`: folder with game profiles. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\reflektortts\profiles`).
- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the game is used. Without it, games run without the overlay.

The first run downloads the default voice (about 60 MB).

## In the game

Press **Ctrl+Shift+R** to open the ReflektorTTS panel. From top to bottom it follows a line through the app: the game and its sources, the text processing stages, and the output (language, voice, game sound, pause, subtitles). It also shows the last line read. See [overlay/README.md](overlay/README.md).

## Voices

- **Piper** voices, downloaded on first use into `%LOCALAPPDATA%\reflektortts\voices`. The default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset.
- **Windows** voices installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish).

The chosen voice is saved in `%LOCALAPPDATA%\reflektortts\settings.json`.

## Game sound

While a line is spoken, ReflektorTTS lowers the game's sound, like a *lektor* speaking over the original, and brings it back half a second after the voice stops. By default the game drops to 30% of its own volume; the panel's Output section switches this off or sets the level. Only the game's slider in the Windows volume mixer is changed, not other apps. If ReflektorTTS stops while the game is lowered, the game's own volume is kept in `%LOCALAPPDATA%\reflektortts\lowered-games.json` and put back the next time the game starts.

## Subtitles

ReflektorTTS can also show each line as a subtitle over the game, for example the Polish translation while the original plays. Switch them on under Subtitles in the panel's Output section, where you also set their size and whether they sit at the top or the bottom of the screen. They are at the top by default, so the game's own text, usually at the bottom, stays visible. A subtitle stays while its line is spoken and a moment after, and at least as long as it takes to read, so subtitles also work with speech paused.

## Translation

ReflektorTTS can translate a game into the output language, in the style of a Polish *lektor*. Set the game language (in the panel's Game section) and the output language (in Output); when they differ, profiles with a `translate` stage translate each line before it is spoken. To turn it off, untick `translate` in the panel's Text processing section.

Only English to Polish is available so far. It runs offline on the CPU, at about 0.1 s per line. The model (about 80 MB) is downloaded the first time a line needs it, into `%LOCALAPPDATA%\reflektortts\translation`. It is the English–Polish model of [Argos Translate](https://github.com/argosopentech/argos-translate), derived from an [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) model by Jörg Tiedemann and Santhosh Thottingal and licensed CC-BY 4.0.

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

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).
