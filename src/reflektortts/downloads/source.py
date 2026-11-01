"""The contract every download source follows, so the app shows and handles them all the same way."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from reflektortts.entry_points import load_plugins

GROUP = "reflektortts.downloads"

type Progress = Callable[[int, int | None], None]
"""Called with the bytes downloaded so far and the total, if known."""


class Kind(StrEnum):
    VOICE = "voice"
    TRANSLATION = "translation"


@dataclass(frozen=True)
class Entry:
    """Something the user can download."""

    id: str
    """Unique across sources: the source's name, a colon, and the source's own ID."""
    kind: Kind
    name: str
    languages: tuple[str, ...]
    """ISO 639-1: a voice's language, or a translation's from and to."""
    size: int | None
    """In bytes, if the source knows it."""
    license: str | None
    """As the source publishes it (e.g. a voice's model card), or None if it does not."""
    page: str
    """Where the user can read more about it."""
    installed: bool
    source_title: str
    """The source's name as shown to users, e.g. "Argos Translate"."""


class DownloadError(Exception):
    """A list or a download could not be fetched, or a download is damaged; the message says what to do."""


class UnknownDownloadError(DownloadError):
    """There is no download with that ID."""


class DownloadStateError(DownloadError):
    """A download cannot be started or removed as things are: it is downloading, or not installed."""


class DownloadSource(Protocol):
    def entries(self, refresh: bool) -> list[Entry]:
        """Its entries, in the languages ReflektorTTS supports. refresh fetches the list from the
        internet, falling back to the cached one; otherwise the cached list is used if there is one."""

    def download(self, entry: Entry, progress: Progress) -> None:
        """Downloads, checks and installs an entry; it can be used right after."""

    def remove(self, entry: Entry) -> None: ...


@dataclass(frozen=True)
class DownloadPlugin:
    """What a download source plugin registers under the reflektortts.downloads entry-point group."""

    name: str
    """Starts its entries' IDs, e.g. "piper"."""
    create: Callable[[Path], DownloadSource]
    """Creates the source, given a folder of its own for cached lists."""


def download_plugins() -> dict[str, DownloadPlugin]:
    return {plugin.name: plugin for plugin in load_plugins(GROUP, DownloadPlugin)}
