# Releasing

How a release of ReflektorTTS is built and published. Windows is the only system with a release for now; Linux gets one when its ports land. Setting up from source and the checks are in [development.md](development.md).

## Building a release

`tools/build_release.py` builds three files into `build\release\`, all uploaded to the release's page on GitHub, under the tag `v<version>`:

- `ReflektorTTS-<version>-windows-x64-setup.exe`: the installer, made by [Inno Setup](https://jrsoftware.org/isinfo.php) 7 from `tools/installer.iss`. It installs the same files as the zip, for the current user into `%LOCALAPPDATA%\Programs\ReflektorTTS` with no administrator rights, or for all users into Program Files; Setup and Uninstall ask the user to quit a running ReflektorTTS first (`desktop/system/session.py` holds named mutexes they look for, one in the user's session and a global one that an all-users install also checks), and uninstalling an install for the current user asks whether to delete their data too. A first install for the current user also offers to start ReflektorTTS with Windows (the same entry `desktop/system/autostart.py` changes), which uninstalling removes for the user who uninstalls. In an install for all users, each user can switch it on in the app; removing that install leaves the other users' entries, which then point to nothing and do no harm.
- `ReflektorTTS-<version>-windows-x64.zip`: `reflektortts.exe` (the desktop app with its own Python, built with PyInstaller), `reflektortts-panel.exe` in a `panel` folder next to it (the settings window, from the 64-bit native build, kept apart so that `reflektortts.exe` is the one program to start), both overlay builds, `LICENSE.txt`, `COPYRIGHT.txt`, a `README.txt` for users, and `THIRD-PARTY-NOTICES.txt`, the committed `THIRD-PARTY-NOTICES.md`. Besides Python, the packages and ReflektorTTS's own files, it holds only Microsoft's Visual C++ runtime (`vcruntime140.dll`, `vcruntime140_1.dll`, `msvcp140.dll` and `msvcp140_1.dll`, which Python and the packages' native libraries need, besides the copy NumPy's package comes with); it leaves out the Universal C Runtime (`ucrtbase.dll` and the `api-ms-win-*` files), which Windows 10 and later include.
- `ReflektorTTS-<version>-sources.zip`: the source code the release offers, as the GPL asks, made by `tools/sources.py`: ReflektorTTS at the commit the release is built from, and the source of every shipped package under the GPL, LGPL or MPL, at the shipped version.

It needs git, Inno Setup 7 (found where its installer puts it, or wherever the `ISCC` environment variable points), the latest [Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) (x64), whose runtime DLLs the build takes from `System32`, the `release` extra, both native builds, with the overlays and the settings window (the `release-x86` and `release` presets, see [development.md](development.md#setting-up-from-source) and [native/README.md](../native/README.md#building)), and every change committed:

```powershell
.venv\Scripts\pip install -e .[release] -c tools\release-constraints.txt
```
```powershell
.venv\Scripts\python tools\build_release.py
```

The version is the one in `pyproject.toml`, which the script reads from the installed package: after changing it, install again (the first command above) before building.

`--draft` builds anyway, to test, from uncommitted changes too, marking what is missing and the files' names.

The Visual C++ runtime comes from one place, the latest [Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) (x64) installed on the build machine, in `System32`, never from whatever else is on `PATH`, such as a JDK's older copies: PyInstaller runs with `PATH` holding only the Windows folders, and `tools/msvc_runtime.py` then puts the four DLLs in from `System32`. The build stops, saying what to install, if one is missing there, if they are not all one version, or if that version is older than the newest Visual C++ toolset that built a shipped library importing them (the runtime works only with programs built by the same toolset or an older one). The build prints the version it shipped.

## Dependencies and notices

`tools/release-constraints.txt` holds the exact version of every package a release is built with, so a release built on GitHub ships the versions it was tested with. After adding or upgrading a dependency and testing the app with it, refresh the file as its first lines say, then write the notices again and commit `THIRD-PARTY-NOTICES.md`:

```powershell
.venv\Scripts\python tools\notices.py
```

`tools/notices.py` writes the license texts of everything a release ships into `THIRD-PARTY-NOTICES.md`: Python, the packages ReflektorTTS needs (from their installed metadata), PyInstaller's parts, the data in `languages.json`, the native programs' libraries and Microsoft's Visual C++ runtime (listed in `NATIVE_NOTICES` there, with their texts in `tools/licenses/`; update both when `native/CMakeLists.txt` moves a library to another version). It follows the installed packages and Python, so run it in the environment above, with the Python version the `Build Windows app` workflow pins (`python-version` in `.github/workflows/build-windows.yml`); change that pin together with the notices. `python tools\notices.py --check` fails unless the file is up to date.

Every license of what a release ships must also pass `tools/licenses.py`, which the `Licenses` check runs (see [development.md](development.md#licenses)): a license that is not on its allow list needs an entry in its `EXCEPTIONS`, for that component, with the reason it may ship.

A release is refused while `THIRD-PARTY-NOTICES.md` is not what `tools/notices.py` writes, a shipped package has no license text, or a shipped package under the GPL, LGPL or MPL has no source listed:

- Add a license text that a package doesn't install, or the notices of parts it contains without them (such as native libraries compiled into it), to `tools/licenses/<package>.txt`, from the project's source at the shipped version.
- Add where a package's source is, for its exact version, to `SOURCES` in `tools/sources.py`.

A new runtime dependency may also need PyInstaller told about it in `tools/build_release.py`: data files, native parts, and modules imported by name.

## Building on GitHub

Releases are built on GitHub the same way, on a clean Windows runner, by the `Build Windows app` workflow (`.github/workflows/build-windows.yml`): it builds both native builds with MSYS2 (the `release-x86` and `release` presets), installs Inno Setup and runs `tools/build_release.py`, which takes the Visual C++ runtime the runner image installs in `System32` (if the image's runtime falls behind a library's toolset, the build stops and says so), then checks that exactly the three release files arrived, under the version's name, with whole zips (the `Windows release files` job). It runs for every pull request, not for pushes, keeping the files on the run's page, and a pull request can be merged only once its `Windows build (x64)` job passes, so a change that breaks the release never reaches `main`. To build `dev` without a pull request, run it by hand (Actions > Build Windows app > Run workflow).

## Publishing a release

The `Release` workflow (`.github/workflows/release.yml`) checks the version and calls that build:

1. Raise the version in `pyproject.toml`, ReflektorTTS's only version.
2. Before tagging, run the workflow by hand on `dev` (Actions > Release > Run workflow): it does everything but the draft, so a change to either workflow shows up before the tag does, and keeps the files on the run's page.
3. Merge `dev` into `main` with a pull request, then push a tag `v<version>` on `main`, where `<version>` is the version in `pyproject.toml`. The workflow builds the files, records where each was built (a provenance attestation, which `gh attestation verify <file> --repo Infinitinker/ReflektorTTS` checks), and drafts the release's page with the three files and their checksums. A tag that differs from the version, or is not on `main`, fails before anything is built.
4. Write the release notes on the draft, then publish it.

The release is drafted only once the `Advisories` workflow (`.github/workflows/advisories.yml`), which the Release workflow calls, passes. It checks every package in `tools/release-constraints.txt` against the published security advisories with [pip-audit](https://pypi.org/project/pip-audit/), and also runs every Monday, for each push to `main` or `dev` and each pull request that changes the pins, and by hand (Actions > Advisories > Run workflow), so an advisory usually shows up before a release does. When it fails, its log names each package, its version, the advisory and the version that fixes it:

- Upgrade the package to a fixed version, test the app with it, and refresh the constraints as the file's first lines say, with the notices (see [Dependencies and notices](#dependencies-and-notices)).
- If no fixed version exists yet, or the fix breaks the app, allow the advisory: add `--ignore-vuln <ID>` to the command in `advisories.yml`, with a comment above it saying why and when to look again. Remove it once the package can be upgraded.

## Signing

The release files are not signed with a paid code-signing certificate: ReflektorTTS is free, and the certificates Windows trusts cost money every year. Windows warns about an unsigned app the first time it starts, and Smart App Control, where it is on, blocks it; the README's [questions](../README.md#questions) tell users how to allow it. A user can still make sure a download is the real one, with the checksums on the release's page or the build attestation, which `gh attestation verify` checks (see above).

The free route for open-source software, the [SignPath Foundation](https://signpath.org/terms), signs only projects with no proprietary components apart from system libraries. The `ctranslate2` package that translation runs on is built with three: the Intel oneAPI Math Kernel Library and the NVIDIA CUDA runtime in `ctranslate2.dll`, and Intel's OpenMP runtime in `libiomp5md.dll` (see `THIRD-PARTY-NOTICES.md`, and the additional permission in `COPYRIGHT` that lets ReflektorTTS be combined with them). While a release ships them, ReflektorTTS can't apply. It could apply only with a CTranslate2 built without them: with an open-source math library in place of Intel's, and without CUDA, which ReflektorTTS doesn't use, since it translates on the CPU.
