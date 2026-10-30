# ReflektorTTS

Your game, read aloud. ReflektorTTS reads game text (dialogue, subtitles, on-screen messages) and speaks it, configured per game through profiles and from inside the game through an overlay.

This is an early version for developers: there is no installer yet. It works with Grand Theft Auto 2 (the 9.6 freeware release), which reads its on-screen messages from the game's memory.

## Setting up (Windows)

You need Python 3.13 and, for the in-game overlay, MSYS2 (see [overlay/README.md](overlay/README.md)).

From the repository root:

```bash
py -3.13 -m venv .venv
```
```bash
.venv\Scripts\pip install -e .[dev]
```

Build the overlay as described in [overlay/README.md](overlay/README.md).

## Running

```bash
.venv\Scripts\python -m reflektortts --profiles profiles --overlay overlay\build\bin
```

ReflektorTTS then waits for a game it has a profile for. When you start the game, it loads the overlay into it and reads its text aloud; when the game exits, it waits for the next one. Stop it with Ctrl+C.

- `--profiles DIR`: folder with game profiles. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\reflektortts\profiles`).
- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the game is used. Without it, games run without the overlay.

The first run downloads the default voice (about 60 MB).

## In the game

Press **Ctrl+Shift+R** to open the ReflektorTTS panel: it shows the last line read, pauses and resumes reading, and switches the voice. See [overlay/README.md](overlay/README.md).

## Voices

- **Piper** voices, downloaded on first use into `%LOCALAPPDATA%\reflektortts\voices`. The default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset.
- **Windows** voices installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish).

The chosen voice is saved in `%LOCALAPPDATA%\reflektortts\settings.json`.

## Local API

Every UI talks to the core through the same local API on `http://127.0.0.1:47821/v1`:

| Request | Does |
|---|---|
| `GET /v1/status` | The game being read, the voice, and whether reading is paused |
| `GET /v1/voices` | Voices available now |
| `PATCH /v1/settings` with `{"voice": "windows:Microsoft Adam"}` | Switches and saves the voice |
| `POST /v1/pause`, `POST /v1/resume` | Pauses or resumes reading |
| `GET /v1/events` (WebSocket) | The status, then `line`, `error` and `status` events as they happen |

## Game profiles

Each game is described by one JSON file in [profiles/](profiles/README.md), which explains the format.

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
