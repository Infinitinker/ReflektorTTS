# Development

How to set up ReflektorTTS from source, run it, and run the checks and tests that every pull request must pass. [architecture.md](architecture.md) explains how the code is organized, and [releasing.md](releasing.md) how a release is built and published.

ReflektorTTS is released for Windows. Linux is the second platform, planned: it has no release yet, but its checks and tests run in CI, so the code stays portable until the Linux ports land.

## Requirements (Windows)

- [Python](https://www.python.org/downloads/) 3.13, with the `py` launcher and Tk (both come with python.org's installer).
- [Git](https://git-scm.com/).
- For the native code (the overlay and the settings window): [MSYS2](https://www.msys2.org/), with its 32-bit and 64-bit MinGW toolchains, CMake and Ninja; [native/README.md](../native/README.md#on-windows-with-msys2) lists the packages. For the C++ checks, also clang-format and clang-tidy (see [C++ checks](#c-checks)).
- For building a release: Inno Setup 7 (see [releasing.md](releasing.md)).

## Setting up from source

The commands below are for PowerShell or the Command Prompt, run from the repository root:

```powershell
py -3.13 -m venv .venv
```
```powershell
.venv\Scripts\pip install -e .[dev]
```

This installs ReflektorTTS with everything it needs, and the `dev` extra adds the tools for tests and checks.

Then build the native code, both builds, as [native/README.md](../native/README.md#building) describes. The 32-bit build, from the **MSYS2 MINGW32** shell in the repository root:

```bash
cmake -S native --preset release-x86 && cmake --build native/build
```

The 64-bit build, with the settings window, from the **MSYS2 MINGW64** shell:

```bash
cmake -S native --preset release && cmake --build native/build64
```

The presets are in `native/CMakePresets.json`: `release` builds into `native/build64`, `release-x86` into `native/build`, `debug` a 64-bit build with debug information into `build/native-debug`, and `ci` is what the C++ checks configure. Each also writes `compile_commands.json` for editors and clang-tidy.

## Running from source

The desktop app, as users run it: double-click `start.bat` in the repository root, or run

```powershell
.venv\Scripts\reflektortts-desktop --overlay native\build\bin --overlay native\build64\bin
```

Logs are written to `%LOCALAPPDATA%\ReflektorTTS\logs` (on Linux `~/.local/state/ReflektorTTS/log`), which the Settings tab's **Open logs folder** button opens. To see the log while working on the code, run ReflektorTTS without the window, in a console, and stop it with Ctrl+C:

```powershell
.venv\Scripts\python -m reflektortts --overlay native\build\bin --overlay native\build64\bin
```

Both take the same options:

- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the app is used. Without it, apps run without the overlay. A release finds its overlay builds next to `reflektortts.exe` by itself. The desktop app also finds the settings window (`reflektortts-panel.exe`, which the 64-bit build makes) in the first of these folders that has it; a release has it in the `panel` folder next to `reflektortts.exe`.
- `--profiles DIR`: folder with your own profiles, used next to the bundled ones. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\ReflektorTTS\profiles`).

## Checks

The `Checks` workflow (`.github/workflows/checks.yml`) runs every check below for each push to `main` and `dev` and for each pull request; a newer push cancels the run still going. Run them yourself before pushing. Its jobs:

- `Lint`: Ruff and the import contracts, once, on Linux.
- `Windows Python checks` and `Linux Python checks`: types and tests, on each system.
- `Licenses`: the licenses of everything a release ships, on Windows.
- `C++ checks`: the include directions, clang-format and clang-tidy, on Windows.

Once a month Dependabot opens a pull request to `dev` with new versions of the actions the workflows and the shared actions in `.github/actions/` use (`.github/dependabot.yml`).

### Lint

Ruff's lint rules and formatting (configured in `pyproject.toml`):

```powershell
.venv\Scripts\python -m ruff check
```
```powershell
.venv\Scripts\python -m ruff format --check
```

`ruff format` without `--check` formats the files, and `ruff check --fix` applies the safe fixes.

The directions imports run in, as [architecture.md](architecture.md) describes them: the desktop app follows the core only through the local API, plugins are found through their entry points and never import each other, platform code stays in its platform modules, and so on. They are the contracts in `[tool.importlinter]` in `pyproject.toml`, each named after its rule, and [import-linter](https://import-linter.readthedocs.io/) checks them:

```powershell
.venv\Scripts\lint-imports
```

It reads the imports from the source text, so it gives the same result on every system. An import a contract must allow goes into the contract's `ignore_imports`, with a comment saying why.

### Types and tests

```powershell
.venv\Scripts\python -m pytest
```
```powershell
.venv\Scripts\python -m mypy
```

mypy checks the code as it runs on your system. To check it as it runs on the other one too, add `--platform linux` on Windows, or `--platform win32` on Linux:

```powershell
.venv\Scripts\python -m mypy --platform linux
```

Tests live in `tests/`, mirroring `src/reflektortts/` (the tests for `src/reflektortts/stages/tracker.py` are in `tests/stages/test_tracker.py`), together with their fakes, and run without a game, a GPU or the network. The tests of the developer tools are in `tests/tools/`. On Linux, the tests that open a window need a display: CI runs them with `xvfb-run -a` (see [Linux checks on Windows (WSL)](#linux-checks-on-windows-wsl)).

### Licenses

Every license of what a release ships (Python, the Python packages, PyInstaller's parts, the data in `languages.json` and the native programs' libraries) must be on the allow list in `tools/licenses.py`, or be named for that one component in its `EXCEPTIONS`, with the reason it may ship. The check reads the installed packages, so run it in the environment releases are built from, the `release` extra with the exact versions a release ships:

```powershell
.venv\Scripts\pip install -e .[release] -c tools\release-constraints.txt
```
```powershell
.venv\Scripts\python tools\licenses.py
```

It lists every component with its license and fails, naming them, when a license is not allowed or an exception is no longer needed. It runs on Windows because a release ships Windows-only packages.

### C++ checks

The C++ code in `native/` is checked from the repository root. First, that each part includes headers only in the directions [native/README.md](../native/README.md) writes down (`shared/` nothing from `overlay/` or `panel/`, and each folder of `overlay/src/` only from the folders listed above it). It needs only Python:

```powershell
.venv\Scripts\python tools\check_includes.py
```

A new folder in `native/overlay/src/` goes into `OVERLAY_FOLDERS` in `tools/check_includes.py`, at its place in the order, and into native/README.md.

The formatting, with clang-format (configured in `.clang-format`), and the static analysis, with clang-tidy (configured in `.clang-tidy`, where each check turned off says why), run in the **MSYS2 MINGW64** shell. Install them once:

```bash
pacman -S --needed mingw-w64-x86_64-clang mingw-w64-x86_64-clang-tools-extra
```

Then, in the repository root:

```bash
git ls-files 'native/*.cpp' 'native/*.h' | xargs clang-format --dry-run --Werror
```

The same with `-i` in place of `--dry-run --Werror` formats the files. clang-tidy reads the compile commands of the `ci` preset, a 64-bit build that only needs configuring:

```bash
cmake -S native --preset ci
```
```bash
git ls-files 'native/*.cpp' | xargs -P 4 -n 1 clang-tidy -p build/native-ci --quiet
```

Any finding fails it. CI checks the 64-bit build's code only, so code that only the 32-bit build compiles (an `#else` of `_WIN64`) is not checked there.

### Generated files

The icon of ReflektorTTS is drawn in code by `tools/draw_icon.py`, into `src/reflektortts/desktop/icon.ico` and the README's `docs/images/icon.png`. After changing the drawing, run it from the repository root:

```powershell
.venv\Scripts\python tools\draw_icon.py
```

The languages ReflektorTTS knows, with their names, codes and code pages, are in `src/reflektortts/languages.json`, generated by `tools/languages.py` from Unicode CLDR (through Babel, in the `dev` extra) and the other sources its docstring lists. After upgrading Babel, run it from the repository root and review the diff:

```powershell
.venv\Scripts\python tools\languages.py
```

What a language has besides, such as a voice preview sentence (`SAMPLES` in `src/reflektortts/languages.py`) or rules for spelling out numbers (`stages/normalize/languages/`), is added by hand.

`THIRD-PARTY-NOTICES.md` is generated too, by `tools/notices.py`; [releasing.md](releasing.md#dependencies-and-notices) says when.

## End-to-end tests

One smoke test, in `tests/e2e/`, runs the desktop app from source as a user does, and follows it through the local API as any client could. The app starts and lists the bundled profiles and the languages; it enables the VLC integration and finds a fake VLC (`tests/e2e/fake_vlc.py`, a small web server that answers as VLC's web interface does, run as a program named `vlc.exe` or `vlc`); it reads the subtitle of the video that VLC plays through the VLC profile's stages, notices VLC closing, and logs no errors. The usual test run leaves it out, so run it on its own:

```powershell
.venv\Scripts\python -m pytest -m e2e
```

- **Close ReflektorTTS and VLC first.** The test stops at once if either runs: the app's port is fixed, and a running VLC would be read instead of the fake one.
- **Your own files are never touched.** The app and VLC get per-user folders of their own, inside the output folder, so your settings, profiles, downloads and VLC's settings stay as they are. The window opens for a few seconds, and if Windows has a voice for English, it reads the test line aloud.
- **The output** goes to the folder in `E2E_OUTPUT`, or else `build\e2e`. The folder is deleted with everything in it before each run, so give `E2E_OUTPUT` a folder of its own. It holds `report.json` (the steps that passed and how long each took, the one that failed and why, and what the test saw), what the app and the fake VLC printed (`reflektortts-console.log`, `fake-vlc.log`), the per-user folders of the run in `home`, with the app's logs, and, on a CI runner only, a screenshot of the screen (`screen.png`).

The `E2E tests` workflow (`.github/workflows/e2e.yml`) runs the test for every push to `main` and `dev` and for every pull request, in two jobs, `Windows E2E tests` and `Linux E2E tests` (Xvfb, with stalonetray as the tray), and on request (Actions > E2E tests > Run workflow, on any branch). Each keeps the output folder as an artifact, with the report in the job summary. You need not run the test before every commit; run it after changes to how the app starts, finds apps or reads VLC.

## Branches

`main` is the stable version; day-to-day work happens on `dev`. Work on a branch from `dev` and open the pull request to `dev`; changes reach `main` only through a pull request from `dev`. Every push to `main` and `dev`, merging a pull request too, runs the Checks and the E2E tests; the Windows app is built for every pull request, by the release and on request.

`main` is protected by a branch ruleset (Settings > Rules > Rulesets, "Default branch protection"): it can be changed only through pull requests, and it cannot be deleted or force-pushed. A pull request can be merged once these checks pass, each from the GitHub Actions app: `Lint`, `Windows Python checks`, `Linux Python checks`, `Licenses` and `C++ checks` (all the jobs of the `Checks` workflow), and `Windows build (x64)` (the `Build Windows app` workflow, which builds pull requests but not pushes). The ruleset names the jobs, so renaming one means changing it there too.

## Linux checks on Windows (WSL)

On Windows, the Linux jobs can run in WSL 2 with Ubuntu 26.04, the release the Linux runners use, in a clone of its own inside WSL: a `.venv` made on Windows doesn't run on Linux, and files on the Windows drives are slow to reach from WSL.

Run them before pushing a change that touches Linux: platform code (anything that checks `sys.platform`, such as `desktop/system/tray_host.py` or `desktop/system/folders.py`), paths and the per-user folders, packaging and dependencies, or the Linux CI jobs. Other changes can leave the Linux jobs to CI, which runs them for every push.

In the Ubuntu shell, install the system packages the Linux jobs install: PortAudio, which plays sound, Xvfb, which gives the window's tests a display, and stalonetray, a tray for the end-to-end test:

```bash
sudo apt-get update && sudo apt-get install -y libportaudio2 xvfb stalonetray
```

Ubuntu 26.04's own Python is newer than the 3.13 ReflektorTTS uses, so install 3.13 from the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa), with venv and Tk, next to the system's Python:

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get install -y python3.13 python3.13-venv python3.13-tk
```

Clone your Windows checkout into `~/Projekty`, so commits you haven't pushed are checked too, and set it up. If your checkout is somewhere other than `D:\Projekty\ReflektorTTS`, use its path (`D:\` is `/mnt/d/`), and replace `dev` with the branch you work on:

```bash
git clone --branch dev /mnt/d/Projekty/ReflektorTTS ~/Projekty/ReflektorTTS
```
```bash
cd ~/Projekty/ReflektorTTS && python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

The clone is only for running the checks: make and commit changes in the Windows checkout, and `git pull` in the clone brings them in (`git fetch`, then `git checkout <branch>`, another branch). Build and test in the clone, never in the checkout on `/mnt/d`.

Then, in `~/Projekty/ReflektorTTS`, with the environment active (`. .venv/bin/activate`), run what each Linux job runs.

**Lint** (`checks.yml`):

```bash
python -m ruff check && python -m ruff format --check && lint-imports
```

**Linux Python checks** (`checks.yml`):

```bash
python -m mypy && xvfb-run -a python -m pytest
```

**Linux E2E tests** (`e2e.yml`), with a tray on the screen first:

```bash
xvfb-run -a -s "-screen 0 1920x1080x24" sh -c 'stalonetray & python -m tests.e2e.wait_for_tray && python -m pytest -m e2e'
```

**Windows release files** (`build-windows.yml`) and the Release workflow's **Check the version** and **Draft the release** run on Linux too, but only check a build's files, the tag and the version, and draft the release on GitHub: they have nothing to run locally.
