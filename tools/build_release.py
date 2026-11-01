"""Builds ReflektorTTS.exe, the desktop app with its own Python, into build/release/dist/ReflektorTTS.

PyInstaller does not see what ReflektorTTS finds only while it runs, so it is told: plugins are
found through entry points (the package's metadata) and imported by name, the profiles, schemas
and icon are data files, and some libraries bring native parts or data of their own.

Needs the release extra: pip install -e .[desktop,translate,release]
Run from the repository root: python tools/build_release.py
"""

from importlib.metadata import version
from pathlib import Path

import PyInstaller.__main__

ENTRY = Path("src/reflektortts/desktop/__main__.py")
ICON = Path("src/reflektortts/desktop/icon.ico")
BUILD = Path("build/release")
NAME = "ReflektorTTS"

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


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    version_file = BUILD / "version.txt"
    version_file.write_text(version_info(version("reflektortts")), "utf-8")
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


if __name__ == "__main__":
    main()
