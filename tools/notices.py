"""Collects the license notices of everything a release of ReflektorTTS ships: the Python packages
it needs (followed through their installed metadata, with the extras the release includes),
Python itself, and the overlay's libraries. Nothing is typed by hand, so the notices follow the
packages; a package without license text stops the release."""

import re
import sys
from importlib.metadata import Distribution, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE)", re.IGNORECASE)
KEPT_LICENSES = Path("tools/licenses")
"""License texts of packages that install none, as <canonical package name>.txt, taken from each
project's source."""
OVERLAY_NOTICES = Path("THIRD_PARTY_NOTICES")
"""The overlay's libraries, which CMake fetches; kept by hand in the repository."""
RULE = "=" * 80


class MissingNoticeError(Exception):
    """A shipped package has no license text to include."""


def shipped_distributions(root: str, extras: tuple[str, ...]) -> list[Distribution]:
    """Every installed package root needs, with its extras, sorted by name; root itself is not
    included."""
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

    visit(root, frozenset(extras))
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


def license_texts(package: Distribution) -> list[str]:
    """The license files the package installs, else the one kept for it in tools/licenses."""
    files = [file for file in package.files or [] if LICENSE_FILE.match(file.name) and file.suffix != ".py"]
    texts = [text for file in sorted(files, key=str) if (text := (file.read_text(encoding="utf-8") or "").strip())]
    kept = KEPT_LICENSES / f"{canonicalize_name(package.metadata['Name'])}.txt"
    if not texts and kept.is_file():
        texts = [kept.read_text("utf-8").strip()]
    return texts


def notices(root: str, extras: tuple[str, ...], draft: bool) -> str:
    """The text of THIRD_PARTY_NOTICES.txt. Raises MissingNoticeError naming every package without
    license text, unless draft, which marks them in the text instead."""
    packages = shipped_distributions(root, extras)
    missing = [package.metadata["Name"] for package in packages if not license_texts(package)]
    if missing and not draft:
        raise MissingNoticeError(
            f"No license text found for: {', '.join(missing)}. Add each to {KEPT_LICENSES} from the project's source."
        )
    sections = [
        "Third-party notices\n\nReflektorTTS (GPL-3.0-or-later, see LICENSE) ships with the following software; their "
        "licenses require these notices to come with it. The program was packaged with PyInstaller, whose bootloader "
        "is GPL-2.0-or-later with an exception that puts no conditions on the packaged program."
    ]
    python = Path(sys.base_prefix) / "LICENSE.txt"
    sections.append(
        _section(
            f"Python {sys.version.split()[0]}",
            "PSF-2.0, with the licenses of the libraries it ships",
            [python.read_text("utf-8").strip()],
        )
    )
    for package in packages:
        name = f"{package.metadata['Name']} {package.version}"
        texts = license_texts(package) or ["LICENSE TEXT MISSING: a draft build; add it before releasing."]
        sections.append(_section(name, license_name(package), texts))
    overlay = OVERLAY_NOTICES.read_text("utf-8")
    sections.append(overlay[overlay.index(RULE) :].strip())
    return "\n\n\n".join(sections) + "\n"


def _section(name: str, license: str, texts: list[str]) -> str:
    return f"{RULE}\n{name}\nLicense: {license}\n{RULE}\n\n" + "\n\n---\n\n".join(texts)
