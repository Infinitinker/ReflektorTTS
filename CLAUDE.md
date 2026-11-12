# ReflektorTTS

Reads an app's text aloud (dialogues, cutscene subtitles, messages) and can optionally translate it in the Polish "lektor" style: one voice over the original soundtrack. Configured per app through profiles, and from inside the app through an overlay.

The design is in `docs/architecture.md`; plugin contracts in `docs/plugins.md`, the local API in `docs/api.md`. Keep them current when the code changes.

## Language and naming

- Everything is written in English: code, comments, docs, commit messages, UI strings.
- The name is **ReflektorTTS** wherever it names the app: prose, UI, the per-user folders (`%LOCALAPPDATA%\ReflektorTTS`, set in `user_dirs.py`), the install folders, the release files (`ReflektorTTS-<version>-windows-x64-setup.exe` and the like) and the names other programs see (the autostart entry, the named mutexes, the User-Agent). It is `reflektortts`, with no dash or underscore, in the code's names and the program files: PyPI package, import name, plugin entry-point groups (`reflektortts.sources`), `reflektortts.exe` and `reflektortts-panel.exe`. The GitHub repository is `Infinitinker/ReflektorTTS`, written like the app's name.
- Commit scopes: `core`, `api`, `desktop`, `overlay`, `panel`, `profiles`, `sources`, `stages`, `translation`, `tts`, `integrations`, `downloads`, `release`. Commits follow Conventional Commits, such as `fix(overlay): keep the panel on top`.

## Open source

- The project will be published on GitHub under **GPL-3.0-or-later**, so others can use it and contribute profiles. GPL is required anyway: `piper-tts` (with espeak-ng) is GPL-3.0.
- Every new dependency must have a GPL-3.0-compatible license (MIT, BSD, Apache-2.0, LGPL, GPL). Check the license before adding one.
- Voice models have their own licenses (in each voice's model card). Check them before bundling a voice or making it a default; never bundle non-commercial-only voices.
- Write code, docs and commit history as if strangers will read them: no personal paths, secrets or machine-specific settings in the repo.

## Principles

The goal is clean code, modularity, portability, and that other people can install and use ReflektorTTS without help.

### Clean code
- Small modules with one job each. If a file needs a section comment to separate unrelated parts, split it.
- A plugin is a single module until it needs several files, then a package in its plugin folder. Code that runs in a separate process gets its own folder. See "How the folders are organized" in `docs/architecture.md`.
- Type hints on all public functions and classes. Use dataclasses or protocols for data and contracts, not loose dicts passed around.
- No dead code, commented-out code or speculative abstractions. Build interfaces from the existing cases (the `memory`, `avalanche` and `vlc` sources) and validate them on the next one (STT); don't design for imagined ones.
- Errors are explicit: raise specific exceptions, and never swallow them silently. A failing plugin must not take down the core: a source, stage or sink that fails is reported as a `source.error`, `stage.error` or `sink.error` event, and a plugin that cannot be loaded is logged and skipped.
- Use `logging`, not `print`.
- Tests live in `tests/`, mirroring `src/reflektortts/` (e.g. `tests/stages/test_tracker.py`), together with their fakes; nothing test-only goes in `src/`. They run without a running app, GPU or network. Hardware- and app-dependent parts sit behind interfaces so they can be faked. The exception is the end-to-end smoke test in `tests/e2e/`, which runs the desktop app from source against a fake VLC, only when asked for (`pytest -m e2e`).

### Modularity
- Sources, processing stages and outputs are plugins behind the `Source`, `Stage` and `Sink` protocols. Adding a plugin must not require changes in the core or the UI.
- Each plugin declares its settings as JSON Schema; UIs generate forms from it.
- Core rule: **module ≠ process**. Split code into modules everywhere; use a separate process only for isolation, heavy resources (TTS, STT, GPU) or code that must live elsewhere (the overlay DLL).
- The core runs headless. Every UI (overlay, desktop) is a client of the same versioned local API (`/v1`, HTTP + WebSocket on 127.0.0.1).
- Logic lives in Python. The C++ overlay only draws UI, captures input and grabs frames.

### Portability
- Windows is the main platform, Linux the second one; macOS is out of scope. The core and the UIs must not depend on any OS.
- Platform-specific code (window capture, OCR engine, process memory, audio loopback) lives only inside plugins or behind a small interface with one implementation per OS. No `win32` imports in core modules.
- Use `pathlib` and never hardcode paths. User data (profiles, settings, logs, model cache) goes in the per-user directories (e.g. via `platformdirs`), never next to the code or in the repo.
- Keep dependencies few and justified. Every runtime dependency is required, so all of ReflektorTTS works after one install; heavy ones are imported only when first needed. Extras are only for tools that are not part of the app (`dev`, `release`). Models (voices, translation) are data, downloaded only when the user asks.

### Ease of use
- A new user should get from download to hearing an app read aloud without editing files or using a terminal. Sensible defaults: a working voice, a ready profile for at least one known app.
- One profile = one app = one JSON file with a `version` field and migrations, so profiles can be shared and stay readable after upgrades.
- Community profiles are a core feature: the profile format has a published JSON Schema, profiles are validated against it, and writing one is documented for non-programmers.
- Error messages say what went wrong and what to do about it, in user terms ("App window not found: is the app running?"), not stack traces.
- Everything configurable in the overlay must work without Alt+Tab; older games often crash when they lose focus.
- Write user-facing docs (install, first run, writing a profile) alongside the features, not after.

## Tooling

- Python development uses a plain `venv` in `.venv/` at the repo root (Python 3.13) with `pip`. Keep `pyproject.toml` standard (PEP 621, no package-manager-specific sections), so contributors can use any tool.
- The C++ code (the overlay and what it shares, in `native/`) builds with CMake; see `native/README.md`.
- Releases are an installer (Inno Setup 7, `tools/installer.iss`) and a zip of the same files to run without installing, built by `tools/build_release.py` with PyInstaller (the `release` extra); see "Building a release" in `CONTRIBUTING.md`. A new runtime dependency may need PyInstaller told about it there (data files, native parts, modules imported by name), its license text must reach `THIRD_PARTY_NOTICES.txt` (`tools/notices.py`), and if it is under the GPL, LGPL or MPL, its source must be listed in `tools/sources.py`.
