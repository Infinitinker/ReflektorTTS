"""Builds a portable release of ReflektorTTS: build/release/ReflektorTTS-<version>-windows-x64.zip,
with one ReflektorTTS folder inside. Unpacked, it runs without installing anything.

The folder holds ReflektorTTS.exe (the desktop app with its own Python, built by PyInstaller), the
32- and 64-bit overlay builds, LICENSE.txt, THIRD_PARTY_NOTICES.txt and README.txt.

PyInstaller does not see what ReflektorTTS finds only while it runs, so it is told: plugins are
found through entry points (the package's metadata) and imported by name, the profiles, schemas
and icon are data files, and some libraries bring native parts or data of their own.

Needs the release extra and both overlay builds (see overlay/README.md):
    pip install -e .[desktop,translate,release]
Run from the repository root:
    python tools/build_release.py           (a release)
    python tools/build_release.py --draft   (to test: allows a placeholder source address and
                                             missing license texts, marked in the zip's name)
"""

import argparse
import shutil
from importlib.metadata import metadata, version
from pathlib import Path

import PyInstaller.__main__
from notices import notices

ENTRY = Path("src/reflektortts/desktop/__main__.py")
ICON = Path("src/reflektortts/desktop/icon.ico")
BUILD = Path("build/release")
NAME = "ReflektorTTS"
EXTRAS = ("desktop", "translate")
"""The extras a release includes; their packages are bundled and their notices collected."""
OVERLAY_BUILDS = {"x86": Path("overlay/build/bin"), "x64": Path("overlay/build64/bin")}
OVERLAY_FILES = ("reflektortts-overlay.dll", "reflektortts-inject.exe")
PLACEHOLDER = "OWNER"
"""In the source address until the repository is published (pyproject.toml, [project.urls])."""

COLLECT = {
    "--copy-metadata": ["reflektortts"],
    "--collect-submodules": ["reflektortts", "num2words", "winrt"],
    "--collect-data": ["reflektortts", "piper", "sacremoses"],
    "--collect-binaries": ["ctranslate2"],
    "--collect-all": ["_sounddevice_data"],
}
"""What PyInstaller is told to take, by option:
- reflektortts: its entry points (metadata), every plugin module, and its data files;
- num2words: one module per language, imported by name;
- winrt: the Windows speech voices' modules, in a namespace package;
- piper: the espeak-ng data it phonemizes with;
- sacremoses: the Moses tokenizer's word lists, for translation;
- ctranslate2: its native libraries;
- _sounddevice_data: the PortAudio library sound is played with.
"""

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

License
  ReflektorTTS is free software under the GPL-3.0-or-later (LICENSE.txt).
  Source code: {source}
  The third-party software it includes, and its licenses: THIRD_PARTY_NOTICES.txt
"""


def version_info(release: str) -> str:
    """The exe's Windows version resource. Windows names the app by its file description, e.g. in
    notifications; without one it shows the file name, ReflektorTTS.exe."""
    numbers = (*(int(part) for part in release.split(".")[:3]), 0)
    strings = {
        "FileDescription": NAME,
        "ProductName": NAME,
        "InternalName": NAME,
        "OriginalFilename": f"{NAME}.exe",
        "FileVersion": release,
        "ProductVersion": release,
        "LegalCopyright": "GPL-3.0-or-later",
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


def build_exe(release: str) -> Path:
    """Runs PyInstaller; returns the folder it built."""
    BUILD.mkdir(parents=True, exist_ok=True)
    version_file = BUILD / "version.txt"
    version_file.write_text(version_info(release), "utf-8")
    arguments = [
        str(ENTRY),
        f"--name={NAME}",
        "--windowed",
        "--onedir",
        "--noconfirm",
        "--clean",
        f"--icon={ICON.resolve()}",
        f"--version-file={version_file.resolve()}",
        f"--distpath={BUILD / 'dist'}",
        f"--workpath={BUILD / 'work'}",
        f"--specpath={BUILD}",
    ]
    for option, packages in COLLECT.items():
        arguments += [f"{option}={package}" for package in packages]
    PyInstaller.__main__.run(arguments)
    return BUILD / "dist" / NAME


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
    if PLACEHOLDER in source and not draft:
        raise SystemExit(f"The source address is still a placeholder ({source}): set it in pyproject.toml.")
    third_party = notices("reflektortts", EXTRAS, draft)

    folder = build_exe(release)
    copy_overlay(folder)
    (folder / "THIRD_PARTY_NOTICES.txt").write_text(third_party, "utf-8", newline="\r\n")
    (folder / "LICENSE.txt").write_text(Path("LICENSE").read_text("utf-8"), "utf-8", newline="\r\n")
    readme = README.format(version=release, source=source)
    (folder / "README.txt").write_text(readme, "utf-8", newline="\r\n")

    archive = BUILD / f"{NAME}-{release}-windows-x64{'-draft' if draft else ''}"
    shutil.make_archive(str(archive), "zip", root_dir=folder.parent, base_dir=NAME)
    print(f"Built {archive}.zip")


if __name__ == "__main__":
    main()
