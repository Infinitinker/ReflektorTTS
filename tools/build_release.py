"""Builds a release of ReflektorTTS into build/release, three files uploaded to the release's page:
- ReflektorTTS-<version>-windows-x64-setup.exe, the installer, made by Inno Setup from
  tools/installer.iss;
- ReflektorTTS-<version>-windows-x64.zip, the same files to unpack and run without installing,
  with one ReflektorTTS folder inside;
- ReflektorTTS-<version>-sources.zip, the source code the release offers (see tools/sources.py).

The folder holds reflektortts.exe (the desktop app with its own Python, built by PyInstaller), the
settings window in its panel folder (reflektortts-panel.exe, from the 64-bit native build), the 32-
and 64-bit overlay builds, LICENSE.txt, COPYRIGHT.txt, THIRD-PARTY-NOTICES.txt and README.txt.

PyInstaller does not see what ReflektorTTS finds only while it runs, so it is told: plugins are
found through entry points (the package's metadata) and imported by name, the profiles, schemas
and icon are data files, and some libraries bring native parts or data of their own.

A release is built from a commit, which its README.txt names, so every change must be committed,
THIRD-PARTY-NOTICES.md included: it must be what tools/notices.py writes for the packages installed.
Needs git, Inno Setup 7 (ISCC.exe in its usual folder, or set ISCC to it), the latest Visual C++
Redistributable (x64), whose runtime DLLs the build takes from System32 (tools/msvc_runtime.py),
the release extra and both native builds, with the overlays and the settings window (see
native/README.md):
    pip install -e .[release] -c tools/release-constraints.txt
Run from the repository root:
    python tools/build_release.py           (a release)
    python tools/build_release.py --draft   (to test: allows uncommitted changes, missing license
                                             texts and outdated notices, marked in the files' names)
"""

import argparse
import os
import shutil
import subprocess
from importlib.metadata import metadata, version
from pathlib import Path

import PyInstaller.__main__
from msvc_runtime import (
    RuntimeSourceError,
    check_versions,
    install_runtime,
    runtime_source,
    source_versions,
    system_path,
)
from notices import NOTICES, SHIPPED_AS, is_current, notices, shipped_distributions
from packaging.version import Version
from sources import check_sources, write_sources

ENTRY = Path("src/reflektortts/desktop/__main__.py")
ICON = Path("src/reflektortts/desktop/icon.ico")
BUILD = Path("build/release")
NAME = "ReflektorTTS"
"""The release's name: its files' names, its folder's and the product name in the exe."""
EXE = "reflektortts"
"""The program's file name, without .exe: lowercase, as the package's name."""
OVERLAY_BUILDS = {"x86": Path("native/build/bin"), "x64": Path("native/build64/bin")}
OVERLAY_FILES = ("reflektortts-overlay.dll", "reflektortts-inject.exe")
PANEL = Path("native/build64/bin/reflektortts-panel.exe")
PANEL_FOLDER = "panel"
"""The settings window goes into this folder next to reflektortts.exe, where the desktop app finds it
(RELEASE_FOLDER in desktop/panel/launcher.py), so the one program next to reflektortts.exe is not
mistaken for one to start."""
COLLECT = {
    "--copy-metadata": ["reflektortts"],
    "--collect-submodules": ["reflektortts", "num2words", "winrt"],
    "--collect-data": ["reflektortts", "piper"],
    "--collect-binaries": ["ctranslate2"],
    "--collect-all": ["_sounddevice_data"],
}
"""What PyInstaller is told to take, by option:
- reflektortts: its entry points (metadata), every plugin module, and its data files;
- num2words: one module per language, imported by name;
- winrt: the Windows speech voices' modules, in a namespace package;
- piper: the espeak-ng data it phonemizes with;
- ctranslate2: its native libraries;
- _sounddevice_data: the PortAudio library sound is played with.
"""
AS_SOURCE = ("num2words", "pystray")
"""LGPL packages, shipped as their .py files instead of inside the exe, so users can change or
replace them, as the LGPL asks."""
UNUSED = (
    "_internal/ctranslate2/cudnn64_9.dll",
    "_internal/_sounddevice_data/portaudio-binaries/*-asio.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio32bit.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudioarm64.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio.dylib",
    "_internal/piper/img",
    "_internal/piper/templates",
    "_internal/PIL/_avif.*.pyd",
    "_internal/PIL/_webp.*.pyd",
    "_internal/reflektortts-*.dist-info/direct_url.json",
)
"""Files and folders the collected packages bring that ReflektorTTS does not use, removed from the
build: NVIDIA's cuDNN (translation runs on the CPU), PortAudio builds for ASIO (with Steinberg's SDK)
and other systems, the pages of Piper's web server, Pillow's AVIF and WebP formats (only the icon's
ICO and PNG are used; Pillow skips formats it cannot import), and the path of the folder the build
was installed from."""
COPYRIGHT = Path("COPYRIGHT")
INSTALLER = Path("tools/installer.iss")
ISCC_FOLDERS = {"ProgramW6432": "", "ProgramFiles": "", "ProgramFiles(x86)": "", "LOCALAPPDATA": "Programs"}
"""Where Inno Setup 7's installer puts it, by environment variable: in Program Files for all users
(ProgramW6432 is the 64-bit one also for a 32-bit Python), or in %LOCALAPPDATA%\\Programs for the
current user."""

README = """ReflektorTTS {version}
Your apps, read aloud.

Starting
  Run reflektortts.exe. Its icon appears next to the clock: right-click it to open the
  window, pause reading or quit. Closing the window leaves ReflektorTTS running.

  Start an app ReflektorTTS has a profile for (the window’s Profiles tab lists them): its
  text is read aloud. In apps with the overlay, Ctrl+Shift+R opens the ReflektorTTS panel.
  The Profiles tab’s App settings… button opens the same settings in a window, for any
  app, also while it isn’t running.

Voices and translation
  Windows voices work right away. More voices and translation models are downloaded only
  when you ask for them, in the window’s Voices and Translations tabs.

Your data
  Settings, downloaded voices and models, your own profiles and the logs are kept in
  %LOCALAPPDATA%\\ReflektorTTS, not in this folder. If you installed ReflektorTTS, run a
  newer release’s installer to update it, and Windows Settings > Apps removes it. From the zip, replace this
  folder with a newer release to update, and delete this folder and that one to remove it.

Antivirus
  The overlay works by loading into the app, as in-game overlays do, which antivirus
  programs may distrust. If yours blocks reflektortts-inject.exe in the overlay folder,
  allow it to use the overlay; ReflektorTTS reads apps without the overlay too.

Online games
  Use ReflektorTTS only in single-player and offline games. Anti-cheat software may treat
  the overlay and reading a game’s memory as cheating, which can get your account banned.

License
  ReflektorTTS is free software under the GPL-3.0-or-later (LICENSE.txt), with an additional
  permission for the libraries translation is built with (COPYRIGHT.txt).
  {copyright}.
  The third-party software it includes, and their licenses: THIRD-PARTY-NOTICES.txt

Source code
  This release is built from {source}, commit
  {commit}.
  {sources}, on the release’s page
  ({source}/releases/tag/v{version}), holds that source code and the source code
  of the third-party software under the GPL, LGPL or MPL that this release includes.
"""


def version_info(release: str, copyright: str) -> str:
    """The exe's Windows version resource. Windows names the app by its file description, e.g. in
    notifications; without one it shows the file name, reflektortts.exe."""
    numbers = version_numbers(release)
    strings = {
        "FileDescription": NAME,
        "ProductName": NAME,
        "InternalName": EXE,
        "OriginalFilename": f"{EXE}.exe",
        "FileVersion": release,
        "ProductVersion": release,
        "LegalCopyright": copyright,
    }
    table = ", ".join(f"StringStruct({key!r}, {value!r})" for key, value in strings.items())
    return (
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3F, flags=0x0, "
        "OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), "
        f"kids=[StringFileInfo([StringTable('040904B0', [{table}])]), "
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n"
    )


def version_numbers(release: str) -> tuple[int, int, int, int]:
    """The four numbers of a Windows version: the release's first three, padded with zeros, and a
    zero, also for pre-releases (0.2.0rc1 is 0.2.0.0)."""
    major, minor, patch = (*Version(release).release, 0, 0)[:3]
    return major, minor, patch, 0


def source_address() -> str:
    for entry in metadata("reflektortts").get_all("Project-URL") or []:
        label, _, address = entry.partition(", ")
        if label == "Source":
            return str(address)
    raise SystemExit("pyproject.toml has no Source address in [project.urls].")


def copyright_line() -> str:
    """The copyright notice in COPYRIGHT, e.g. "Copyright (C) 2026 Infinitinker"."""
    return next(line for line in COPYRIGHT.read_text("utf-8").splitlines() if line.startswith("Copyright"))


def source_commit(draft: bool) -> str:
    """The commit the release is built from. A release needs every change committed; a draft may
    have changes, which the commit then lacks."""
    changes = git("status", "--porcelain")
    if changes and not draft:
        raise SystemExit("Commit every change first: a release is built from a commit, which its README.txt names.")
    return git("rev-parse", "HEAD")


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], check=True, capture_output=True, text=True).stdout.strip()


def iscc() -> Path:
    """Inno Setup's compiler: the ISCC environment variable, or where Inno Setup 7 installs it."""
    if chosen := os.environ.get("ISCC"):
        return Path(chosen)
    for variable, below in ISCC_FOLDERS.items():
        if variable in os.environ:
            compiler = Path(os.environ[variable], below, "Inno Setup 7", "ISCC.exe")
            if compiler.is_file():
                return compiler
    raise SystemExit("Install Inno Setup 7 (https://jrsoftware.org/isdl.php), or set ISCC to its ISCC.exe.")


def write_hooks(folder: Path) -> Path:
    """PyInstaller hooks that ship the AS_SOURCE packages as .py files, with all their modules."""
    folder.mkdir(parents=True, exist_ok=True)
    for package in AS_SOURCE:
        hook = (
            "from PyInstaller.utils.hooks import collect_submodules\n\n"
            f"hiddenimports = collect_submodules({package!r})\n"
            'module_collection_mode = "py"\n'
        )
        (folder / f"hook-{package}.py").write_text(hook, "utf-8")
    return folder


def build_exe(release: str, copyright: str) -> Path:
    """Runs PyInstaller; returns the folder it built, named as the release (PyInstaller names it as
    the exe)."""
    BUILD.mkdir(parents=True, exist_ok=True)
    version_file = BUILD / "version.txt"
    version_file.write_text(version_info(release, copyright), "utf-8")
    hooks = write_hooks(BUILD / "hooks")
    arguments = [
        str(ENTRY),
        f"--name={EXE}",
        "--windowed",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--noupx",
        f"--icon={ICON.resolve()}",
        f"--version-file={version_file.resolve()}",
        f"--distpath={BUILD / 'dist'}",
        f"--workpath={BUILD / 'work'}",
        f"--specpath={BUILD}",
        f"--additional-hooks-dir={hooks.resolve()}",
    ]
    for option, packages in COLLECT.items():
        arguments += [f"{option}={package}" for package in packages]
    # PyInstaller looks for the DLLs binaries import on PATH too: only the Windows folders, so nothing
    # else installed on the build machine is taken (tools/msvc_runtime.py).
    path = os.environ["PATH"]
    os.environ["PATH"] = system_path()
    try:
        PyInstaller.__main__.run(arguments)
    finally:
        os.environ["PATH"] = path
    return (BUILD / "dist" / EXE).rename(BUILD / "dist" / NAME)


def remove_unused(folder: Path) -> None:
    for pattern in UNUSED:
        found = list(folder.glob(pattern))
        if not found:
            raise SystemExit(f"The build has no {pattern} to remove: update UNUSED in tools/build_release.py.")
        for path in found:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def build_installer(compiler: Path, folder: Path, release: str, copyright: str, name: str) -> Path:
    """Compiles tools/installer.iss into build/release/<name>.exe, installing folder."""
    numbers = ".".join(str(number) for number in version_numbers(release))
    defines = {
        "AppVersion": release,
        "NumericVersion": numbers,
        "Copyright": copyright,
        "SourceDir": folder.resolve(),
        "OutputDir": BUILD.resolve(),
        "IconFile": ICON.resolve(),
    }
    arguments = [str(compiler), "/Q", f"/F{name}", *(f"/D{key}={value}" for key, value in defines.items())]
    subprocess.run([*arguments, str(INSTALLER)], check=True)
    return BUILD / f"{name}.exe"


def copy_overlay(folder: Path) -> None:
    for name, build in OVERLAY_BUILDS.items():
        missing = [file for file in OVERLAY_FILES if not (build / file).is_file()]
        if missing:
            raise SystemExit(f"Build the overlay first (see native/README.md): {build} has no {', '.join(missing)}.")
        target = folder / "overlay" / name
        target.mkdir(parents=True, exist_ok=True)
        for file in OVERLAY_FILES:
            shutil.copy2(build / file, target / file)


def copy_panel(folder: Path) -> None:
    if not PANEL.is_file():
        raise SystemExit(f"Build the settings window first (see native/README.md): {PANEL} is missing.")
    target = folder / PANEL_FOLDER
    target.mkdir(exist_ok=True)
    shutil.copy2(PANEL, target / PANEL.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Builds the release files of ReflektorTTS.")
    parser.add_argument("--draft", action="store_true", help="a build to test, not to publish")
    draft = parser.parse_args().draft
    release = version("reflektortts")
    source = source_address()
    commit = source_commit(draft)
    compiler = iscc()
    copyright = copyright_line()
    third_party = notices("reflektortts", draft)
    if not draft and not is_current(third_party):
        raise SystemExit(f"{NOTICES} is out of date: run python tools/notices.py, then commit it.")
    packages = shipped_distributions("reflektortts")
    check_sources(packages)
    mark = "-draft" if draft else ""
    sources = f"{NAME}-{release}-sources.zip"

    runtime_folder = runtime_source()
    try:
        check_versions(source_versions(runtime_folder), None)  # Before the long build, what is missing at least.
        folder = build_exe(release, copyright)
        remove_unused(folder)
        runtime = install_runtime(folder / "_internal", runtime_folder)
    except RuntimeSourceError as error:
        raise SystemExit(str(error)) from error
    print(f"Visual C++ runtime {'.'.join(map(str, runtime))} from {runtime_folder}")
    copy_overlay(folder)
    copy_panel(folder)
    (folder / SHIPPED_AS).write_text(third_party, "utf-8", newline="\r\n")
    for name in ("LICENSE", "COPYRIGHT"):
        (folder / f"{name}.txt").write_text(Path(name).read_text("utf-8"), "utf-8", newline="\r\n")
    readme = README.format(version=release, source=source, copyright=copyright, commit=commit, sources=sources)
    (folder / "README.txt").write_text(readme, "utf-8", newline="\r\n")

    archive = BUILD / f"{NAME}-{release}-windows-x64{mark}"
    shutil.make_archive(str(archive), "zip", root_dir=folder.parent, base_dir=NAME)
    installer = build_installer(compiler, folder, release, copyright, f"{NAME}-{release}-windows-x64-setup{mark}")
    sources_archive = BUILD / f"{NAME}-{release}-sources{mark}.zip"
    write_sources(sources_archive, NAME, release, commit, packages)
    print(f"Built {installer}, {archive}.zip and {sources_archive}")


if __name__ == "__main__":
    main()
