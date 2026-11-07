"""Collects the license notices of everything a release of ReflektorTTS ships: the Python packages
it needs (followed through their installed metadata), Python itself, PyInstaller's parts, and the
overlay's libraries. The notices follow the installed packages; a package without license text stops
the release."""

import re
import sys
from importlib.metadata import Distribution, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|ThirdPartyNotices)", re.IGNORECASE)
KEPT_LICENSES = Path("tools/licenses")
"""Texts added to what a package installs, as <canonical package name>.txt (python.txt for Python
itself), taken from each project's source: the license of a package that installs none, and the
notices of parts it contains without them, such as the native libraries compiled into it."""
PACKAGED_WITH = ("pyinstaller", "pyinstaller-hooks-contrib")
"""Build tools whose parts end up in the release: PyInstaller's bootloader and run-time hooks."""
OVERLAY_NOTICES = Path("THIRD_PARTY_NOTICES")
"""The overlay's libraries, which CMake fetches; kept by hand in the repository."""
COPYLEFT = re.compile(r"GPL|General Public|MPL|Mozilla Public", re.IGNORECASE)
RULE = "=" * 80


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
    """The text of THIRD_PARTY_NOTICES.txt. Raises MissingNoticeError naming every package without
    license text, unless draft, which marks them in the text instead."""
    packages = shipped_distributions(root)
    tools = [distribution(name) for name in PACKAGED_WITH]
    missing = [package.metadata["Name"] for package in packages + tools if not license_texts(package)]
    if missing and not draft:
        raise MissingNoticeError(
            f"No license text found for: {', '.join(missing)}. Add each to {KEPT_LICENSES} from the project's source."
        )
    sections = [
        "Third-party notices\n\nReflektorTTS (GPL-3.0-or-later, see LICENSE.txt and COPYRIGHT.txt) ships with the "
        "following software; their licenses require these notices to come with it. The source code of the parts "
        "under the GPL, LGPL or MPL is in the release's sources zip (see README.txt)."
    ]
    python = Path(sys.base_prefix) / "LICENSE.txt"
    sections.append(
        _section(
            f"Python {sys.version.split()[0]}",
            "PSF-2.0, with the licenses of the libraries it ships",
            [python.read_text("utf-8").strip(), *_kept("python")],
        )
    )
    for package in packages + tools:
        name = f"{package.metadata['Name']} {package.version}"
        texts = license_texts(package) or ["LICENSE TEXT MISSING: a draft build; add it before releasing."]
        sections.append(_section(name, license_name(package), texts))
    overlay = OVERLAY_NOTICES.read_text("utf-8")
    sections.append(overlay[overlay.index(RULE) :].strip())
    return "\n\n\n".join(sections) + "\n"


def _kept(name: str) -> list[str]:
    kept = KEPT_LICENSES / f"{name}.txt"
    return [kept.read_text("utf-8").strip()] if kept.is_file() else []


def _section(name: str, license: str, texts: list[str]) -> str:
    return f"{RULE}\n{name}\nLicense: {license}\n{RULE}\n\n" + "\n\n---\n\n".join(texts)
