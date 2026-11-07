"""Builds a portable release of ReflektorTTS: build/release/ReflektorTTS-<version>-windows-x64.zip,
with one ReflektorTTS folder inside. Unpacked, it runs without installing anything. Next to it,
ReflektorTTS-<version>-sources.zip holds the source code the release offers (see tools/sources.py);
both are uploaded to the release's page.

The folder holds ReflektorTTS.exe (the desktop app with its own Python, built by PyInstaller), the
32- and 64-bit overlay builds, LICENSE.txt, COPYRIGHT.txt, THIRD_PARTY_NOTICES.txt and README.txt.

PyInstaller does not see what ReflektorTTS finds only while it runs, so it is told: plugins are
found through entry points (the package's metadata) and imported by name, the profiles, schemas
and icon are data files, and some libraries bring native parts or data of their own.

A release is built from a commit, which its README.txt names, so every change must be committed.
Needs git, the release extra and both overlay builds (see overlay/README.md):
    pip install -e .[release]
Run from the repository root:
    python tools/build_release.py           (a release)
    python tools/build_release.py --draft   (to test: allows uncommitted changes and missing license
                                             texts, marked in the zip's name)
"""

import argparse
import shutil
import subprocess
from importlib.metadata import metadata, version
from pathlib import Path

import PyInstaller.__main__
from notices import notices, shipped_distributions
from packaging.version import Version
from sources import check_sources, write_sources

ENTRY = Path("src/reflektortts/desktop/__main__.py")
ICON = Path("src/reflektortts/desktop/icon.ico")
BUILD = Path("build/release")
NAME = "ReflektorTTS"
OVERLAY_BUILDS = {"x86": Path("overlay/build/bin"), "x64": Path("overlay/build64/bin")}
OVERLAY_FILES = ("reflektortts-overlay.dll", "reflektortts-inject.exe")
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
    "_internal/piper/hebrew/*.onnx",
    "_internal/piper/tashkeel/*.onnx",
    "_internal/piper/img",
    "_internal/piper/templates",
    "_internal/PIL/_avif.*.pyd",
    "_internal/PIL/_webp.*.pyd",
    "_internal/reflektortts-*.dist-info/direct_url.json",
)
"""Files and folders the collected packages bring that ReflektorTTS does not use, removed from the
build: NVIDIA's cuDNN (translation runs on the CPU), PortAudio builds for ASIO (with Steinberg's SDK)
and other systems, Piper's models that add vowel marks to Hebrew and Arabic text (ReflektorTTS
offers English and Polish voices), the pages of Piper's web server, Pillow's AVIF and WebP formats (only the icon's
ICO and PNG are used; Pillow skips formats it cannot import), and the path of the folder the build
was installed from."""
COPYRIGHT = Path("COPYRIGHT")

README = """ReflektorTTS {version}
Your apps, read aloud.

Starting
  Run ReflektorTTS.exe. Its icon appears next to the clock: right-click it to open the
  window, pause reading or quit. Closing the window leaves ReflektorTTS running.

  Start an app ReflektorTTS has a profile for (the window's Profiles tab lists them): its
  text is read aloud. In apps with the overlay, Ctrl+Shift+R opens the ReflektorTTS panel.

Voices and translation
  Windows voices work right away. More voices and translation models are downloaded only
  when you ask for them, in the window's Voices and Translations tabs.

Your data
  Settings, downloaded voices and models, your own profiles and the logs are kept in
  %LOCALAPPDATA%\\ReflektorTTS, not in this folder. To update, replace this folder with a
  newer release. To remove ReflektorTTS, delete this folder and that one.

Antivirus
  The overlay works by loading into the app, as in-game overlays do, which antivirus
  programs may distrust. If yours blocks reflektortts-inject.exe in the overlay folder,
  allow it to use the overlay; ReflektorTTS reads apps without the overlay too.

Online games
  Use ReflektorTTS only in single-player and offline games. Anti-cheat software may treat
  the overlay and reading a game's memory as cheating, which can get your account banned.

License
  ReflektorTTS is free software under the GPL-3.0-or-later (LICENSE.txt), with an additional
  permission for the libraries translation is built with (COPYRIGHT.txt).
  {copyright}.
  The third-party software it includes, and their licenses: THIRD_PARTY_NOTICES.txt

Source code
  This release is built from {source}, commit
  {commit}.
  {sources}, on the release's page
  ({source}/releases/tag/v{version}), holds that source code and the source code
  of the third-party software under the GPL, LGPL or MPL that this release includes.
"""


def version_info(release: str, copyright: str) -> str:
    """The exe's Windows version resource. Windows names the app by its file description, e.g. in
    notifications; without one it shows the file name, ReflektorTTS.exe. Its four numbers are the
    release's first three, padded with zeros, and a zero, also for pre-releases (0.2.0rc1 is 0.2.0.0)."""
    numbers = (*(Version(release).release + (0, 0))[:3], 0)
    strings = {
        "FileDescription": NAME,
        "ProductName": NAME,
        "InternalName": NAME,
        "OriginalFilename": f"{NAME}.exe",
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
    """Runs PyInstaller; returns the folder it built."""
    BUILD.mkdir(parents=True, exist_ok=True)
    version_file = BUILD / "version.txt"
    version_file.write_text(version_info(release, copyright), "utf-8")
    hooks = write_hooks(BUILD / "hooks")
    arguments = [
        str(ENTRY),
        f"--name={NAME}",
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
    PyInstaller.__main__.run(arguments)
    return BUILD / "dist" / NAME


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


def copy_overlay(folder: Path) -> None:
    for name, build in OVERLAY_BUILDS.items():
        missing = [file for file in OVERLAY_FILES if not (build / file).is_file()]
        if missing:
            raise SystemExit(f"Build the overlay first (see overlay/README.md): {build} has no {', '.join(missing)}.")
        target = folder / "overlay" / name
        target.mkdir(parents=True, exist_ok=True)
        for file in OVERLAY_FILES:
            shutil.copy2(build / file, target / file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Builds a portable release of ReflektorTTS.")
    parser.add_argument("--draft", action="store_true", help="a build to test, not to publish")
    draft = parser.parse_args().draft
    release = version("reflektortts")
    source = source_address()
    commit = source_commit(draft)
    copyright = copyright_line()
    third_party = notices("reflektortts", draft)
    packages = shipped_distributions("reflektortts")
    check_sources(packages)
    mark = "-draft" if draft else ""
    sources = f"{NAME}-{release}-sources.zip"

    folder = build_exe(release, copyright)
    remove_unused(folder)
    copy_overlay(folder)
    (folder / "THIRD_PARTY_NOTICES.txt").write_text(third_party, "utf-8", newline="\r\n")
    for name in ("LICENSE", "COPYRIGHT"):
        (folder / f"{name}.txt").write_text(Path(name).read_text("utf-8"), "utf-8", newline="\r\n")
    readme = README.format(version=release, source=source, copyright=copyright, commit=commit, sources=sources)
    (folder / "README.txt").write_text(readme, "utf-8", newline="\r\n")

    archive = BUILD / f"{NAME}-{release}-windows-x64{mark}"
    shutil.make_archive(str(archive), "zip", root_dir=folder.parent, base_dir=NAME)
    sources_archive = BUILD / f"{NAME}-{release}-sources{mark}.zip"
    write_sources(sources_archive, NAME, release, commit, packages)
    print(f"Built {archive}.zip and {sources_archive}")


if __name__ == "__main__":
    main()
