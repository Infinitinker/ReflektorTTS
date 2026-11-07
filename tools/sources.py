"""Collects the source code a release offers next to it, as its licenses ask: ReflektorTTS's own, at
the commit the release is built from, and that of every shipped package under the GPL, LGPL or MPL,
at the shipped version. Where each package's source is, is kept by hand in SOURCES, so a new
copyleft package or version stops the release until its source is added there."""

import shutil
import subprocess
import urllib.request
import zipfile
from importlib.metadata import Distribution
from pathlib import Path

from notices import is_copyleft

SOURCES: dict[str, list[str]] = {
    "num2words 0.5.14": ["https://files.pythonhosted.org/packages/source/n/num2words/num2words-0.5.14.tar.gz"],
    "piper-tts 1.8.0": [
        "https://github.com/OHF-Voice/piper1-gpl/archive/refs/tags/v1.8.0.tar.gz",
        # The espeak-ng commit piper-tts 1.8.0 builds in (its CMakeLists.txt).
        "https://github.com/espeak-ng/espeak-ng/archive/724808c5a83f9ef95fdd0db886ba7ba537ff224a.tar.gz",
    ],
    "pystray 0.19.5": ["https://github.com/moses-palmer/pystray/archive/refs/tags/v0.19.5.tar.gz"],
    "tqdm 4.70.1": ["https://files.pythonhosted.org/packages/source/t/tqdm/tqdm-4.70.1.tar.gz"],
}
"""Source archives of the copyleft packages, by "<package> <version>": the project's source at the
released version, and the sources of what its build compiles in."""

README = """Source code of ReflektorTTS {version}

{name}.tar.gz is ReflektorTTS itself, at commit
{commit},
with the scripts that build the release (tools/build_release.py).

third-party/ holds the source code of the software under the GPL, LGPL or MPL that the release
includes, at the versions it includes:
{packages}
"""


class MissingSourceError(Exception):
    """A shipped copyleft package has no source listed in SOURCES."""


def copyleft_packages(packages: list[Distribution]) -> list[str]:
    """The "<package> <version>" of each package whose license asks for its source to be offered."""
    return [f"{package.metadata['Name']} {package.version}" for package in packages if is_copyleft(package)]


def check_sources(packages: list[Distribution]) -> None:
    """Raises MissingSourceError naming every copyleft package with no source in SOURCES."""
    missing = [package for package in copyleft_packages(packages) if package not in SOURCES]
    if missing:
        raise MissingSourceError(
            f"No source listed for: {', '.join(missing)}. Add where each one's source is to SOURCES in {__file__}."
        )


def write_sources(archive: Path, name: str, version: str, commit: str, packages: list[Distribution]) -> None:
    """Writes the sources zip: ReflektorTTS at commit, as git has it, and the sources of the copyleft
    packages, downloaded. Call check_sources first."""
    shipped = copyleft_packages(packages)
    with zipfile.ZipFile(archive, "w") as sources:
        own = subprocess.run(
            ["git", "archive", "--format=tar.gz", f"--prefix={name}-{version}/", commit],
            check=True,
            capture_output=True,
        ).stdout
        sources.writestr(f"{name}-{version}.tar.gz", own)
        for package in shipped:
            folder = package.replace(" ", "-")
            for url in SOURCES[package]:
                with urllib.request.urlopen(url, timeout=60) as response:
                    file_name = response.headers.get_filename() or url.rsplit("/", 1)[-1]
                    with sources.open(f"third-party/{folder}/{file_name}", "w") as target:
                        shutil.copyfileobj(response, target)
        listing = "\n".join(f"- {package}: third-party/{package.replace(' ', '-')}/" for package in shipped)
        readme = README.format(version=version, name=f"{name}-{version}", commit=commit, packages=listing)
        sources.writestr("README.txt", readme.replace("\n", "\r\n"))
