"""Checks that everything a release of ReflektorTTS ships is under a license on the allow list:
Python itself, the Python packages (as tools/notices.py finds them, PyInstaller's parts included),
the data taken from other projects and the native programs' libraries. A license that is not on the
list is allowed only for the component an entry in EXCEPTIONS names, with the reason it may ship.

It reads the installed packages, so run it in the environment releases are built from, from the
repository root:
    pip install -e .[release] -c tools/release-constraints.txt
    python tools/licenses.py
It prints every component with its license and exits with 1, naming them, when a license is not
allowed or an exception is no longer needed.
"""

import re
import sys
from collections.abc import Iterable, Sequence
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from typing import NamedTuple

from notices import DATA_NOTICES, NATIVE_NOTICES, PACKAGED_WITH, Notice, license_name, shipped_distributions
from packaging.utils import canonicalize_name

ROOT = "reflektortts"
ALLOWED = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MIT-0",
        "MIT-CMU",
        "PSF-2.0",
        "Zlib",
    }
)
"""The licenses everything ReflektorTTS ships may be under, as SPDX identifiers: the GPL-compatible
ones CLAUDE.md's "Open source" names (MIT, BSD, Apache-2.0, LGPL, GPL), and the permissive PSF-2.0
(Python's), Zlib and MIT-CMU (Pillow's HPND)."""
ALIASES = {
    "3-Clause BSD License": "BSD-3-Clause",
    "Apache 2.0": "Apache-2.0",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "LGPLv3": "LGPL-3.0-only",
    "MIT License": "MIT",
}
"""SPDX identifiers for the names packages give their licenses in, where the name says which one it
is. Names that do not ("BSD License", "LGPL") need an exception saying what the license text reads."""


class Allowance(NamedTuple):
    """A license allowed for one component only, and why it may ship."""

    component: str
    license: str
    reason: str


INTEL_NVIDIA = (
    "Proprietary runtime libraries in ctranslate2.dll and libiomp5md.dll (tools/licenses/ctranslate2.txt), which "
    "ReflektorTTS may be combined with under the additional permission in COPYRIGHT (GPL section 7)."
)
CONTAINED = {
    "ctranslate2": (
        "LicenseRef-Intel-Simplified-Software-License",
        "LicenseRef-Intel-EULA-Developer-Tools",
        "LicenseRef-NVIDIA-CUDA-EULA",
    ),
}
"""The licenses of parts a package contains that its metadata does not name, by canonical package name,
as its text in tools/licenses lists them."""
EXCEPTIONS = (
    Allowance(
        "regex",
        "CNRI-Python",
        "The code taken from Python's re module, under the CNRI license that is part of Python's own, whose "
        "choice of law was amended for works combined with GPL code.",
    ),
    Allowance(
        "tqdm",
        "MPL-2.0",
        "Section 3.3 of the MPL-2.0 allows combining it with GPL code; its source is in the sources zip "
        "(tools/sources.py).",
    ),
    Allowance("numpy", "CC0-1.0", "A public domain dedication, compatible with the GPL."),
    Allowance("colorama", "BSD License", "BSD-3-Clause, as its LICENSE.txt reads."),
    Allowance("mock", "BSD License", "BSD-2-Clause, as its LICENSE.txt reads."),
    Allowance("num2words", "LGPL", "LGPL-2.1, as its COPYING reads."),
    Allowance(
        "pyinstaller",
        "GPL-2.0-only",
        "GPL-2.0-or-later, as its COPYING.txt reads; the bootloader it puts in the release ships under its "
        "Bootloader Exception, and its run-time hooks under Apache-2.0.",
    ),
    Allowance(
        "pyinstaller-hooks-contrib",
        "GPL-2.0-only",
        "GPL-2.0-or-later, as its LICENSE reads, for the hooks used while building; the run-time hooks the "
        "release contains are under Apache-2.0.",
    ),
    Allowance("pyinstaller-hooks-contrib", "Apache Software License", "Apache-2.0, as its LICENSE reads."),
    *(Allowance("ctranslate2", license, INTEL_NVIDIA) for license in CONTAINED["ctranslate2"]),
    Allowance("unicode-cldr", "Unicode-3.0", "A permissive license, compatible with the GPL."),
    Allowance(
        "native-mingw-w64",
        "several, below",
        "The GCC runtime libraries are under the GPL-3.0 with the GCC Runtime Library Exception; the MinGW-w64 "
        "runtime and winpthreads under permissive notices (tools/licenses/native-mingw-w64.txt).",
    ),
    Allowance(
        "msvc-runtime",
        "Microsoft Visual C++ Redistributable terms",
        "Microsoft's terms for the Visual C++ Redistributable allow shipping its DLLs, unmodified, with a "
        "program that uses them; and they are System Libraries in the sense of section 1 of the GPL-3.0, "
        "so the GPL does not require their source. Covers the four DLLs tools/msvc_runtime.py installs and "
        "the msvcp140-<hash>.dll in numpy.libs.",
    ),
)
"""Licenses allowed for one component each, by its key: the canonical package name, the name of a
notice's text in tools/licenses without .txt, or python."""


class Component(NamedTuple):
    """Something a release ships, with the license it is under."""

    key: str
    """What EXCEPTIONS name it by."""
    title: str
    license: str
    """As its metadata or notice names it: an SPDX expression or a name."""
    contains: tuple[str, ...] = ()
    """Licenses of parts it contains that the license above leaves out."""


class Verdict(NamedTuple):
    """What the check found for one component."""

    component: Component
    refused: tuple[str, ...]
    """Its licenses that are neither allowed nor excepted for it."""
    excepted: tuple[str, ...]
    """Its licenses allowed by an exception."""


def components(root: str) -> list[Component]:
    """Everything a release built from the installed packages ships, as tools/notices.py lists it."""
    python = f"Python {sys.version_info.major}.{sys.version_info.minor}"
    found = [Component("python", python, "PSF-2.0")]
    packages = shipped_distributions(root) + [distribution(name) for name in PACKAGED_WITH]
    found += [package_component(package) for package in packages]
    found += [notice_component(notice) for notice in DATA_NOTICES + NATIVE_NOTICES]
    return found


def package_component(package: Distribution) -> Component:
    """A Python package, with the license its metadata names."""
    key = canonicalize_name(package.metadata["Name"])
    title = f"{package.metadata['Name']} {package.version}"
    return Component(key, title, license_name(package), CONTAINED.get(key, ()))


def notice_component(notice: Notice) -> Component:
    """Data or a native library, keyed by its text's name in tools/licenses."""
    return Component(notice.file.removesuffix(".txt"), notice.name, notice.license)


def judge(component: Component, exceptions: Iterable[Allowance] = EXCEPTIONS) -> Verdict:
    """Which of the component's licenses are refused, and which allowed by an exception. Of the choices
    an expression with OR offers, the one with the fewest refused, then excepted, licenses counts."""
    excepted = {allowance.license for allowance in exceptions if allowance.component == component.key}
    contained = [license for license in component.contains if license not in ALLOWED]
    options = []
    for choice in alternatives(component.license, excepted):
        licenses = sorted({license for license in choice if license not in ALLOWED} | set(contained))
        refused = tuple(license for license in licenses if license not in excepted)
        allowed = tuple(license for license in licenses if license in excepted)
        options.append((refused, allowed))
    refused, allowed = min(options, key=lambda option: (len(option[0]), len(option[1])))
    return Verdict(component, refused, allowed)


def alternatives(license: str, known: Iterable[str] = ()) -> list[frozenset[str]]:
    """The choices a license expression offers, each the licenses that all apply. A name in ALIASES
    becomes its SPDX identifier; a name in known, a comma-separated list of names (as classifiers give
    them) or text that is no SPDX expression is taken as it is."""
    license = ALIASES.get(license, license)
    if license in ALLOWED or license in known:
        return [frozenset({license})]
    if ", " in license:
        parts = [ALIASES.get(part, part) for part in license.split(", ")]
        return [frozenset(parts)]
    try:
        return _Expression(license).parse()
    except ValueError:
        return [frozenset({license})]


class _Expression:
    """An SPDX license expression, read as the OR of choices, each the AND of licenses."""

    def __init__(self, text: str) -> None:
        self.tokens: list[str] = re.findall(r"[()]|[^\s()]+", text)
        self.position = 0

    def parse(self) -> list[frozenset[str]]:
        choices = self._or()
        if self.position != len(self.tokens):
            raise ValueError(f"Unexpected {self.tokens[self.position]!r}")
        return choices

    def _or(self) -> list[frozenset[str]]:
        choices = self._and()
        while self._take("OR"):
            choices = choices + self._and()
        return choices

    def _and(self) -> list[frozenset[str]]:
        choices = self._term()
        while self._take("AND"):
            rights = self._term()
            choices = [left | right for left in choices for right in rights]
        return choices

    def _term(self) -> list[frozenset[str]]:
        if self._take("("):
            choices = self._or()
            if not self._take(")"):
                raise ValueError("Missing )")
            return choices
        name = self._identifier()
        if self._take("WITH"):
            name = f"{name} WITH {self._identifier()}"
        return [frozenset({ALIASES.get(name, name)})]

    def _identifier(self) -> str:
        if self.position == len(self.tokens):
            raise ValueError("Missing a license")
        token = self.tokens[self.position]
        if token in ("(", ")") or token.upper() in ("AND", "OR", "WITH"):
            raise ValueError(f"Unexpected {token!r}")
        self.position += 1
        return token

    def _take(self, token: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position].upper() == token:
            self.position += 1
            return True
        return False


def unused(verdicts: Sequence[Verdict], exceptions: Iterable[Allowance] = EXCEPTIONS) -> list[Allowance]:
    """The exceptions no component needs: its component is not shipped, or no longer under that license."""
    used = {(verdict.component.key, license) for verdict in verdicts for license in verdict.excepted}
    return [allowance for allowance in exceptions if (allowance.component, allowance.license) not in used]


def report(verdicts: Sequence[Verdict], stale: Sequence[Allowance]) -> list[str]:
    """The lines to print: every component and its license, then what fails the check."""
    lines = []
    for verdict in verdicts:
        component = verdict.component
        license = " + ".join((component.license, *component.contains))
        mark = "NOT ALLOWED" if verdict.refused else "excepted" if verdict.excepted else "ok"
        lines.append(f"{mark:<12}{component.title}: {license}")
    refused = [verdict for verdict in verdicts if verdict.refused]
    if refused:
        lines.append("")
        lines.append("Not on the allow list in tools/licenses.py:")
        lines += [f"  {verdict.component.title}: {', '.join(verdict.refused)}" for verdict in refused]
    if stale:
        lines.append("")
        lines.append("Exceptions in tools/licenses.py no component needs any more; remove them:")
        lines += [f"  {allowance.component}: {allowance.license}" for allowance in stale]
    return lines


def main() -> None:
    try:
        found = components(ROOT)
    except PackageNotFoundError as error:
        raise SystemExit(
            f"{error.name} is not installed. Run this in the environment releases are built from: "
            "pip install -e .[release] -c tools/release-constraints.txt"
        ) from None
    verdicts = [judge(component) for component in found]
    stale = unused(verdicts)
    print("\n".join(report(verdicts, stale)))
    if stale or any(verdict.refused for verdict in verdicts):
        sys.exit(1)
    print(f"\nAll {len(verdicts)} components are under allowed licenses.")


if __name__ == "__main__":
    main()
