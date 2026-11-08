# Contributing to ReflektorTTS

Thank you for helping! Profiles for more games are the most welcome contribution, and you don't need to be a programmer to write one. Fixes, ideas and bug reports are welcome too.

- **Found a bug?** Open an issue with the bug report form. The logs help most: the Settings tab's **Open logs folder** button opens them.
- **Want a game supported?** Open an issue with the app support form, or write its profile yourself (below).
- **Found a security problem?** Report it privately, as [SECURITY.md](SECURITY.md) describes, not in an issue.

Everything in the project is written in English, with American spelling (license, color, canceled). Contributions are accepted under the project's license: the GPL-3.0-or-later with the additional permission in [COPYRIGHT](COPYRIGHT).

## Contributing a profile

A profile is one JSON file that tells ReflektorTTS how to recognize a game and where its text is. [docs/profiles.md](docs/profiles.md) explains the format.

1. In the ReflektorTTS window's Profiles tab, select a bundled profile close to what you need and choose **Copy to edit**, or start a new file in `%LOCALAPPDATA%\ReflektorTTS\profiles\`.
2. Edit it in any text editor, saved as UTF-8, and choose **Reload**. A profile with a mistake is shown as broken, with the reason.
3. Play the game and check that its text is read. List the `sha256` of each build you tested, which a profile with the overlay must do: once a profile lists builds, the Status tab shows the SHA-256 of any other build it meets.
4. Give it a `rating` medal for how far you tested it, from `bronze` (tried briefly) to `platinum` (every text read, tested to the end); [docs/profiles.md](docs/profiles.md) says what each one takes.
5. Share it: open a pull request that adds it to `src/reflektortts/profiles/bundled/`, or attach it to an app support issue.

Name the file after the game and its release year, in lowercase with dashes, like `grand-theft-auto-2-1999.json`.

## Code

### Setting up from source (Windows)

You need Python 3.13 and, for the overlay, MSYS2 (see [native/README.md](native/README.md)). The commands below are for PowerShell or the Command Prompt, run from the repository root:

```powershell
py -3.13 -m venv .venv
```
```powershell
.venv\Scripts\pip install -e .[dev]
```

This installs ReflektorTTS with everything it needs, and the `dev` extra adds the tools for tests and checks. Build the overlay as described in [native/README.md](native/README.md).

### Running from source

The desktop app, as users run it: double-click `start.bat` in the repository root, or run

```powershell
.venv\Scripts\reflektortts-desktop --overlay native\build\bin --overlay native\build64\bin
```

Logs are written to `%LOCALAPPDATA%\ReflektorTTS\Logs`. To see the log while working on the code, run ReflektorTTS without the window, in a console, and stop it with Ctrl+C:

```powershell
.venv\Scripts\python -m reflektortts --overlay native\build\bin --overlay native\build64\bin
```

Both take the same options:

- `--overlay DIR`: folder with an overlay build. Repeat it to give both a 32-bit and a 64-bit build; the one matching the app is used. Without it, apps run without the overlay. A release finds its overlay builds next to `ReflektorTTS.exe` by itself. The desktop app also finds the settings window (`reflektortts-panel.exe`, which the 64-bit build makes) in the first of these folders that has it; a release has it next to `ReflektorTTS.exe`.
- `--profiles DIR`: folder with your own profiles, used next to the bundled ones. Default: `profiles` in your user data folder (`%LOCALAPPDATA%\ReflektorTTS\profiles`).

### Checks

Every pull request is checked by the `Checks` workflow: lint and formatting once, types and tests on both Windows and Linux. Run them yourself first:

```powershell
.venv\Scripts\python -m pytest
```
```powershell
.venv\Scripts\python -m ruff check
```
```powershell
.venv\Scripts\python -m ruff format --check
```
```powershell
.venv\Scripts\python -m mypy
```

mypy checks the code as it runs on your system. To check it as it runs on the other one too, add `--platform linux` on Windows, or `--platform win32` on Linux:

```powershell
.venv\Scripts\python -m mypy --platform linux
```

Tests live in `tests/`, mirroring `src/reflektortts/`, and run without a game, a GPU or the network. [docs/architecture.md](docs/architecture.md) explains how the code is organized, and [docs/plugins.md](docs/plugins.md) how to add sources, processing stages, speech engines and download sources as plugins.

The icon of ReflektorTTS is drawn in code by `tools/draw_icon.py`, into `src/reflektortts/desktop/icon.ico` and the README's `docs/images/icon.png`. After changing the drawing, run it from the repository root:

```powershell
.venv\Scripts\python tools\draw_icon.py
```

### Building a release

`tools/build_release.py` builds three files into `build\release\`, all uploaded to the release's page on GitHub, under the tag `v<version>`:

- `ReflektorTTS-<version>-windows-x64-setup.exe`: the installer, made by [Inno Setup](https://jrsoftware.org/isinfo.php) 7 from `tools/installer.iss`. It installs the same files as the zip, for the current user into `%LOCALAPPDATA%\Programs\ReflektorTTS` with no administrator rights, or for all users into Program Files; Setup and Uninstall ask the user to quit a running ReflektorTTS first (`desktop/system/session.py` holds named mutexes they look for, one in the user's session and a global one that an all-users install also checks), and uninstalling an install for the current user asks whether to delete their data too. A first install for the current user also offers to start ReflektorTTS with Windows (the same entry `desktop/system/autostart.py` changes), which uninstalling removes for the user who uninstalls. In an install for all users, each user can switch it on in the app; removing that install leaves the other users' entries, which then point to nothing and do no harm.
- `ReflektorTTS-<version>-windows-x64.zip`: `ReflektorTTS.exe` (the desktop app with its own Python, built with PyInstaller), `reflektortts-panel.exe` next to it (the settings window, from the 64-bit native build), both overlay builds, `LICENSE.txt`, `COPYRIGHT.txt`, a `README.txt` for users, and `THIRD_PARTY_NOTICES.txt`, generated by `tools/notices.py` from the installed packages' metadata.
- `ReflektorTTS-<version>-sources.zip`: the source code the release offers, as the GPL asks, made by `tools/sources.py`: ReflektorTTS at the commit the release is built from, and the source of every shipped package under the GPL, LGPL or MPL, at the shipped version.

It needs git, Inno Setup 7 (found where its installer puts it, or wherever the `ISCC` environment variable points), the `release` extra and both native builds, with the overlays and the settings window (see [native/README.md](native/README.md)), and every change committed:

```powershell
.venv\Scripts\pip install -e .[release] -c tools\release-constraints.txt
```
```powershell
.venv\Scripts\python tools\build_release.py
```

`tools/release-constraints.txt` holds the exact version of every package a release is built with, so a release built on GitHub ships the versions it was tested with. After adding or upgrading a dependency and testing the app with it, refresh the file as its first lines say.

A release is refused while a shipped package has no license text, or a shipped package under the GPL, LGPL or MPL has no source listed:

- Add a license text that a package doesn't install, or the notices of parts it contains without them (such as native libraries compiled into it), to `tools/licenses/<package>.txt`, from the project's source at the shipped version.
- Add where a package's source is, for its exact version, to `SOURCES` in `tools/sources.py`.

`--draft` builds anyway, to test, from uncommitted changes too, marking what is missing and the files' names.

Releases are built on GitHub by the `Release` workflow (`.github/workflows/release.yml`), the same way, on a clean Windows runner: it builds both native builds with MSYS2, installs Inno Setup and runs `tools/build_release.py`.

- Pushing a tag `v<version>` on `main`, where `<version>` is the version in `pyproject.toml`, builds the release, records where each file was built (a provenance attestation, which `gh attestation verify <file> --repo Infinitinker/ReflektorTTS` checks), and drafts the release's page with the three files and their checksums. Write the release notes there, then publish it.
- A pull request that changes the native code, `pyproject.toml`, the release tools or their constraints builds a release too, to check that it still builds. A run started by hand on the Actions tab builds one to try. Both keep the files on the run's page, without drafting a release.
