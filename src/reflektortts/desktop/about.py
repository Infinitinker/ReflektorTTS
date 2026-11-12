"""What the window tells about ReflektorTTS itself: its version, and where its project page, its
bug reports and its support pages are."""

from dataclasses import dataclass
from importlib.metadata import metadata, version

KO_FI = "https://ko-fi.com/infinitinker"
BUYCOFFEE = "https://buycoffee.to/infinitinker"
"""The support pages, as in .github/FUNDING.yml; buycoffee.to takes BLIK and Polish bank transfers."""
LICENSE = "Free software under the GPL-3.0-or-later. Copyright © 2026 Infinitinker."


@dataclass(frozen=True)
class About:
    version: str
    project: str
    """The project page."""
    issues: str
    """Where to report a problem."""


def about() -> About:
    """From the installed package's metadata, which pyproject.toml fills in."""
    urls = dict(entry.split(", ", 1) for entry in metadata("reflektortts").get_all("Project-URL") or [])
    return About(version=version("reflektortts"), project=urls["Source"], issues=urls["Issues"])
