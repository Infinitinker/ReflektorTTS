# ReflektorTTS

Reads an app's text aloud (dialogues, cutscene subtitles, messages) and can optionally translate it in the Polish "lektor" style: one voice over the original soundtrack. Configured per app through profiles, and from inside the app through an overlay. A Python core and desktop app, with a C++ overlay DLL and settings window in `native/`, released for Windows.

`README.md` is for users and `CONTRIBUTING.md` for contributors. Developer documentation is in `docs/`: `architecture.md` (the design, the code map and how the folders are organized), `development.md` (setup, running from source, every check, the end-to-end tests and the branches), `releasing.md` (how a release is built and published), `interface-texts.md` (the rules for the interface's texts), `plugins.md` (the plugin contracts), `api.md` (the local API) and `profiles.md` (the profile format); the native code is described in `native/README.md`. Keep them current when the code changes.

Code written before these rules is being brought in line with them, stage by stage. Follow the rules in new and changed code, and don't extend what they replace.

## Language and naming

- Everything is written in English: code, comments, docs, commit messages, CI and the interface. Other languages appear only as deliberate data: test data, the language data ReflektorTTS handles (language names, letters, voice preview sentences, rules for spelling out numbers), and examples of it in docs and comments.
- American spelling: color, center, gray, canceled, behavior, license (the noun too). "Dialogue" stays for spoken lines; "dialog" is a window.
- The interface's texts follow the rules in `docs/interface-texts.md`.
- The name is **ReflektorTTS** wherever it names the app: prose, UI, the per-user folders (`%LOCALAPPDATA%\ReflektorTTS`, set in `user_dirs.py`), the install folders, the release files (`ReflektorTTS-<version>-windows-x64-setup.exe`, `ReflektorTTS-<version>-windows-x64.zip` and `ReflektorTTS-<version>-sources.zip`) and the names other programs see (the autostart entry, the named mutexes, the User-Agent). A run from source is **ReflektorTTS Dev** and the end-to-end test's run is **ReflektorTTS E2E**, chosen by the `REFLEKTORTTS_MODE` environment variable (`identity.py`), so neither touches the installed app's folders, mutexes or autostart entry; a release is always ReflektorTTS. It is `reflektortts` in the code's names and the program files: PyPI package, import name, plugin entry-point groups (`reflektortts.sources`), `reflektortts.exe`, `reflektortts-panel.exe`, `reflektortts-overlay.dll`, `reflektortts-inject.exe` and the `reflektortts-desktop` script. The installer's AppId (`tools/installer.iss`) is how Windows and updates recognize the installed app, and it never changes. The GitHub repository is `Infinitinker/ReflektorTTS`, written like the app's name.
- Commits follow Conventional Commits, such as `fix(overlay): keep the panel on top`. The types `build`, `ci` and `docs` take no scope; the others name the part they change, from the list below, and leave the scope out when the change spans several parts.
- Commit scopes: `core`, `api`, `desktop`, `overlay`, `panel`, `profiles`, `sources`, `stages`, `translation`, `tts`, `integrations`, `downloads`, `release`.

## Open source

- The project will be published on GitHub under **GPL-3.0-or-later**, so others can use it and contribute profiles. GPL is required anyway: `piper-tts` (with espeak-ng) is GPL-3.0.
- Every new dependency must have a GPL-3.0-compatible license (MIT, BSD, Apache-2.0, LGPL, GPL). Check the license before adding one. The allow list, as SPDX identifiers, and the exceptions, each with its reason, are in `tools/licenses.py`, which checks everything a release ships.
- Voice models have their own licenses (in each voice's model card). Check them before bundling a voice or making it a default; never bundle non-commercial-only voices.
- Write code, docs and commit history as if strangers will read them: no personal paths, secrets or machine-specific settings in the repo.

## Principles

The goal is clean code, modularity, portability, and that other people can install and use ReflektorTTS without help.

### Clean code
- Small modules with one job each. Every module opens with a doc comment saying what that job is (a module docstring in Python, a `//` comment at the top of a C++ file). If a file needs a section comment to separate unrelated parts, split it.
- A plugin is a single module until it needs several files, then a package in its plugin folder. Code that runs in a separate process gets its own folder. See "How the folders are organized" in `docs/architecture.md`.
- Type hints on all public functions and classes. Use dataclasses or protocols for data and contracts, not loose dicts passed around.
- No dead code, commented-out code or speculative abstractions. Build interfaces from the existing cases (the `memory`, `avalanche` and `vlc` sources) and validate them on the next one (STT); don't design for imagined ones.
- Errors are explicit: raise specific exceptions, and never swallow them silently. A failing plugin must not take down the core: a source, stage or sink that fails is reported as a `source.error`, `stage.error` or `sink.error` event, and a plugin that cannot be loaded is logged and skipped.
- Use `logging`, not `print`.
- Tests live in `tests/`, mirroring `src/reflektortts/` (e.g. `tests/stages/test_tracker.py`), together with their fakes; nothing test-only goes in `src/`. They run without a running app, GPU or network. Hardware- and app-dependent parts sit behind interfaces so they can be faked. The exception is the end-to-end smoke test in `tests/e2e/`, which runs the desktop app from source against a fake VLC; the usual test run leaves it out, and it runs when asked for (`pytest -m e2e`) and in CI.

### Modularity
- Sources, processing stages and outputs are plugins behind the `Source`, `Stage` and `Sink` protocols. Adding a plugin must not require changes in the core or the UI.
- Each plugin declares its settings as JSON Schema; UIs generate forms from it.
- Core rule: **module ≠ process**. Split code into modules everywhere; use a separate process only for isolation, heavy resources (TTS, STT, GPU) or code that must live elsewhere (the overlay DLL).
- The core runs headless. Every UI (overlay, desktop) is a client of the same versioned local API (`/v1`, HTTP + WebSocket on 127.0.0.1).
- Logic lives in Python. The C++ overlay only draws UI, captures input and grabs frames.
- Imports run one way between folders, as `docs/architecture.md` describes. The import-linter contracts in `pyproject.toml` check it for Python, and `tools/check_includes.py` for the C++ in `native/` (the directions in `native/README.md`); a new folder in `native/overlay/src` is added to both the script and the README.

### Portability
- Windows is the main platform and, for now, the only one with a release. Linux is the second one, planned: its checks run in CI, so the code stays portable until the Linux ports land. macOS is out of scope. The core and the UIs must not depend on any OS.
- Platform-specific code (window capture, OCR engine, process memory, audio loopback) lives only inside plugins or behind a small interface with one implementation per OS. No `win32` imports in core modules.
- Use `pathlib` and never hardcode paths. User data (profiles, settings, logs, model cache) goes in the per-user directories (e.g. via `platformdirs`), never next to the code or in the repo.
- Keep dependencies few and justified. Every runtime dependency is required, so all of ReflektorTTS works after one install; heavy ones are imported only when first needed. Extras are only for tools that are not part of the app (`dev`, `release`). Models (voices, translation) are data, downloaded only when the user asks.

### Ease of use
- A new user should get from download to hearing an app read aloud without editing files or using a terminal. Sensible defaults: a working voice, a ready profile for at least one known app.
- One profile = one app = one JSON file with a `version` field and migrations, so profiles can be shared and stay readable after upgrades.
- Community profiles are a core feature: the profile format has a published JSON Schema, profiles are validated against it, and writing one is documented for non-programmers.
- Interface texts follow the rules in `docs/interface-texts.md`. Among them: an error message says what went wrong and what to do about it, in user terms ("App window not found: is the app running?"), not as a stack trace.
- Everything configurable in the overlay must work without Alt+Tab; older games often crash when they lose focus.
- Write user-facing docs (install, first run, writing a profile) alongside the features, not after.

## Tooling

- Python 3.13, in a plain `venv` in `.venv/` at the repo root, with `pip`; a release is built with the patch release pinned in `.github/workflows/build-windows.yml`. Keep `pyproject.toml` standard (PEP 621, no package-manager-specific sections), so contributors can use any tool. Ruff lints and formats, mypy checks types, pytest runs the tests, and import-linter checks the import directions.
- The C++ code (the overlay, the settings window and what they share, in `native/`) is C++20, built with CMake 3.24 or newer and Ninja through the presets in `native/CMakePresets.json` (`release`, `release-x86`, `debug`, `ci`), with MSYS2's GCC: MINGW64 for the 64-bit build, MINGW32 for the 32-bit overlay. clang-format and clang-tidy, from MSYS2's clang, follow `.clang-format` and `.clang-tidy` at the root. See `native/README.md` and `docs/development.md`.
- Releases are an installer (Inno Setup 7, `tools/installer.iss`) and a zip of the same files to run without installing, built by `tools/build_release.py` with PyInstaller (the `release` extra); see `docs/releasing.md`. A new runtime dependency may need PyInstaller told about it there (data files, native parts, modules imported by name), its license must pass `tools/licenses.py`, its license text must reach `THIRD-PARTY-NOTICES.md` (run `tools/notices.py` and commit the file), and if it is under the GPL, LGPL or MPL, its source must be listed in `tools/sources.py`.
- Before committing, run the checks for what changed, from the repository root (`python` is the venv's, `.venv\Scripts\python`, and `lint-imports` is `.venv\Scripts\lint-imports`):
  - For any change to Python: `python -m ruff check`, `python -m ruff format --check` (`python -m ruff format` fixes it), `python -m mypy` (for platform code also `python -m mypy --platform linux`, which checks the code as it runs on Linux), `python -m pytest` and `lint-imports`.
  - For any change in `native/`: `python tools/check_includes.py`; then, in the MSYS2 MINGW64 shell, clang-format with `git ls-files 'native/*.cpp' 'native/*.h' | xargs clang-format --dry-run --Werror` (`clang-format -i <file>` fixes it) and clang-tidy with `cmake -S native --preset ci`, then `git ls-files 'native/*.cpp' | xargs -P 4 -n 1 clang-tidy -p build/native-ci --quiet`; and both builds: `cmake -S native --preset release`, then `cmake --build native/build64` in MINGW64, and `cmake -S native --preset release-x86`, then `cmake --build native/build` in MINGW32.
  - After adding or upgrading a dependency, in the release environment (`python -m pip install -e .[release] -c tools\release-constraints.txt`): the license check, `python tools/licenses.py`, and `python tools/notices.py --check` (when it fails, run `python tools/notices.py` and commit `THIRD-PARTY-NOTICES.md`).
  - For changes that touch Linux (platform code, paths, packaging, the Linux CI jobs): the Linux checks in WSL, as "Linux checks on Windows (WSL)" in `docs/development.md` lists them.
  - The end-to-end test (`python -m pytest -m e2e`) is not needed before each commit: the `E2E tests` workflow runs it for every push to `main` and `dev` and every pull request.
- Branches: `main` is stable, work happens on `dev`, changes reach `main` through pull requests.
