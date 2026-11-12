"""Writes THIRD-PARTY-NOTICES.md, the license notices of everything a release of ReflektorTTS ships:
Python itself, the Python packages it needs (followed through their installed metadata),
PyInstaller's parts, data taken from other projects, the native programs' libraries and Microsoft's
Visual C++ runtime. A release ships the file as THIRD-PARTY-NOTICES.txt.

The notices follow the installed packages, so run it in the environment releases are built from (the
release extra, installed with tools/release-constraints.txt; see "Dependencies and notices" in
docs/releasing.md), and commit the file whenever the dependencies change. A package without license
text stops it. Run from the repository root:
    python tools/notices.py           write THIRD-PARTY-NOTICES.md
    python tools/notices.py --check   fail unless it is up to date
"""

import argparse
import re
import sys
from importlib.metadata import Distribution, distribution
from pathlib import Path
from typing import NamedTuple

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

NOTICES = Path("THIRD-PARTY-NOTICES.md")
SHIPPED_AS = "THIRD-PARTY-NOTICES.txt"
LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|ThirdPartyNotices)", re.IGNORECASE)
KEPT_LICENSES = Path("tools/licenses")
"""Texts added to what a package installs, as <canonical package name>.txt (python.txt for Python
itself), taken from each project's source: the license of a package that installs none, and the
notices of parts it contains without them, such as the native libraries compiled into it. The texts
of data and of the native programs' libraries are kept there too."""
PACKAGED_WITH = ("pyinstaller", "pyinstaller-hooks-contrib")
"""Build tools whose parts end up in the release: PyInstaller's bootloader and run-time hooks."""


class Notice(NamedTuple):
    """Third-party code or data that comes from no Python package, with its text in tools/licenses."""

    name: str
    license: str
    file: str
    about: str = ""
    source: str = ""


DATA_NOTICES = (
    Notice("Unicode CLDR 47 (the language names in languages.json)", "Unicode-3.0", "unicode-cldr.txt"),
    Notice("dotnet/runtime 9.0.0 (the code pages in languages.json)", "MIT", "dotnet-runtime.txt"),
)
"""Data in ReflektorTTS taken from other projects: the language table tools/languages.py generates."""
NATIVE_NOTICES = (
    Notice(
        "Dear ImGui v1.92.9",
        "MIT",
        "native-imgui.txt",
        "Compiled into reflektortts-overlay.dll and reflektortts-panel.exe.",
        "https://github.com/ocornut/imgui",
    ),
    Notice(
        "nlohmann/json v3.12.0",
        "MIT",
        "native-nlohmann-json.txt",
        "Compiled into reflektortts-overlay.dll and reflektortts-panel.exe.",
        "https://github.com/nlohmann/json",
    ),
    Notice(
        "MinHook v1.3.4 (with the Hacker Disassembler Engine)",
        "BSD-2-Clause",
        "native-minhook.txt",
        "Compiled into reflektortts-overlay.dll.",
        "https://github.com/TsudaKageyu/minhook",
    ),
    Notice(
        "SDL 3.4.20 (with yuv2rgb)",
        "Zlib",
        "native-sdl.txt",
        "Compiled into reflektortts-panel.exe.",
        "https://github.com/libsdl-org/SDL",
    ),
    Notice(
        "MinGW-w64 runtime and winpthreads",
        "several, below",
        "native-mingw-w64.txt",
        "reflektortts-overlay.dll, reflektortts-inject.exe and reflektortts-panel.exe are built with MinGW-w64 GCC, "
        "whose runtime is linked into them. The GCC runtime libraries (libgcc, libstdc++) are under the GPL-3.0 with "
        "the GCC Runtime Library Exception, which puts no conditions on the program. The MinGW-w64 runtime and "
        "winpthreads come with these notices.",
        "https://www.mingw-w64.org",
    ),
    Notice(
        "Microsoft Visual C++ runtime",
        "Microsoft Visual C++ Redistributable terms",
        "msvc-runtime.txt",
        "The runtime of the Python packages' native libraries, which tools/build_release.py takes from the "
        "Visual C++ Redistributable installed on the build machine (tools/msvc_runtime.py).",
        "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files",
    ),
)
"""The native libraries a release ships that come from no Python package: those of the native programs
(native/), which CMake fetches at configure time, and Microsoft's Visual C++ runtime. Update an entry
and its text when native/CMakeLists.txt moves to another version."""
COPYLEFT = re.compile(r"GPL|General Public|MPL|Mozilla Public", re.IGNORECASE)


class MissingNoticeError(Exception):
    """A shipped package has no license text to include."""


def shipped_distributions(root: str) -> list[Distribution]:
    """Every installed package root needs, sorted by name; root itself is not included, nor its
    extras (the tools to develop and build it)."""
    found: dict[str, Distribution] = {}
    visited: set[tuple[str, frozenset[str]]] = set()

    def visit(name: str, wanted: frozenset[str]) -> None:
        key = canonicalize_name(name)
        if (key, wanted) in visited:
            return
        visited.add((key, wanted))
        package = distribution(name)
        found[key] = package
        environments = [{"extra": extra} for extra in ("", *wanted)]
        for text in package.requires or []:
            requirement = Requirement(text)
            marker = requirement.marker
            if marker is None or any(marker.evaluate(environment) for environment in environments):
                visit(requirement.name, frozenset(requirement.extras))

    visit(root, frozenset())
    found.pop(canonicalize_name(root))
    return sorted(found.values(), key=lambda package: canonicalize_name(package.metadata["Name"]))


def license_name(package: Distribution) -> str:
    """The license as the package's metadata names it."""
    metadata = package.metadata
    if expression := metadata.get("License-Expression"):
        return str(expression)
    license_field = metadata.get("License") or ""
    if license_field and "\n" not in license_field and len(license_field) <= 100:
        return str(license_field)
    classifiers = [
        classifier.split(" :: ")[-1]
        for classifier in metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    ]
    return ", ".join(classifiers) or "see the license text"


def is_copyleft(package: Distribution) -> bool:
    """Whether the package's license asks for its source to come with copies (GPL, LGPL, MPL)."""
    return bool(COPYLEFT.search(license_name(package)))


def license_texts(package: Distribution) -> list[str]:
    """The license files the package installs, then the text kept for it in tools/licenses."""
    files = [file for file in package.files or [] if LICENSE_FILE.match(file.name) and file.suffix != ".py"]
    texts = [text for file in sorted(files, key=str) if (text := (file.read_text(encoding="utf-8") or "").strip())]
    return texts + _kept(canonicalize_name(package.metadata["Name"]))


def notices(root: str, draft: bool) -> str:
    """The text of THIRD-PARTY-NOTICES.md. Raises MissingNoticeError naming every package without
    license text, unless draft, which marks them in the text instead."""
    packages = shipped_distributions(root)
    tools = [distribution(name) for name in PACKAGED_WITH]
    missing = [package.metadata["Name"] for package in packages + tools if not license_texts(package)]
    if missing and not draft:
        raise MissingNoticeError(
            f"No license text found for: {', '.join(missing)}. Add each to {KEPT_LICENSES} from the project's source."
        )
    python = Path(sys.base_prefix) / "LICENSE.txt"
    parts = [
        "# Third-party notices",
        "ReflektorTTS is free software under the GPL-3.0-or-later (LICENSE, with an additional permission in "
        "COPYRIGHT; LICENSE.txt and COPYRIGHT.txt in a release). It ships with the third-party software listed "
        "here, whose licenses require these notices to come with every copy. The source code of the Python packages "
        "under the GPL, LGPL or MPL is in the release's sources zip (see its README.txt); PyInstaller's bootloader "
        "and run-time hooks ship under the exceptions in their licenses, below.",
        f"This file is written by `python tools/notices.py` from the packages a release is built with; do not edit "
        f"it by hand. A release ships it as {SHIPPED_AS}.",
        "## Python",
        _section(
            f"Python {sys.version_info.major}.{sys.version_info.minor}",
            "PSF-2.0, with the licenses of the libraries it ships",
            [python.read_text("utf-8").strip(), *_kept("python")],
        ),
        "## Python packages",
        "The packages ReflektorTTS needs, and the parts of PyInstaller, which builds the release, that it contains.",
    ]
    for package in packages + tools:
        name = f"{package.metadata['Name']} {package.version}"
        texts = license_texts(package) or ["LICENSE TEXT MISSING: a draft build; add it before releasing."]
        parts.append(_section(name, license_name(package), texts))
    parts.append("## Data")
    parts += [_notice(notice) for notice in DATA_NOTICES]
    parts.append("## Native programs")
    parts.append(
        "The overlay (reflektortts-overlay.dll and reflektortts-inject.exe) and the settings window "
        "(reflektortts-panel.exe) are built from native/ with these libraries."
    )
    parts += [_notice(notice) for notice in NATIVE_NOTICES]
    return "\n\n".join(parts) + "\n"


def _kept(name: str) -> list[str]:
    kept = KEPT_LICENSES / f"{name}.txt"
    return [kept.read_text("utf-8").strip()] if kept.is_file() else []


def _fenced(text: str) -> str:
    """The text in a code block, fenced with more backticks than it holds in a row."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def _section(name: str, license: str, texts: list[str], about: str = "", source: str = "") -> str:
    lines = [f"### {name} ({license})"]
    lines += [line for line in (about, f"Source: {source}" if source else "") if line]
    return "\n\n".join(lines + [_fenced(text) for text in texts])


def _notice(notice: Notice) -> str:
    text = (KEPT_LICENSES / notice.file).read_text("utf-8").strip()
    return _section(notice.name, notice.license, [text], notice.about, notice.source)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Writes {NOTICES}, the third-party notices a release ships.")
    parser.add_argument("--check", action="store_true", help=f"fail unless {NOTICES} is up to date")
    check = parser.parse_args().check
    try:
        text = notices("reflektortts", draft=False)
    except MissingNoticeError as error:
        raise SystemExit(str(error)) from None
    if not check:
        NOTICES.write_text(text, "utf-8", newline="\n")
        print(f"Wrote {NOTICES}")
    elif not is_current(text):
        raise SystemExit(f"{NOTICES} is out of date: run python tools/notices.py and commit it.")


def is_current(text: str) -> bool:
    """Whether the committed THIRD-PARTY-NOTICES.md holds this text."""
    return NOTICES.is_file() and NOTICES.read_text("utf-8").replace("\r\n", "\n") == text


if __name__ == "__main__":
    main()
