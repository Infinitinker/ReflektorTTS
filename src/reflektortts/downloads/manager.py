"""Downloads: every source's entries with their state, and the downloads the user started.

Several downloads can run at once, each on a thread of its own. Their progress is reported as
DownloadEvents, at most a few times a second each.
"""

import contextlib
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from reflektortts.downloads.source import (
    DownloadError,
    DownloadSource,
    DownloadStateError,
    Entry,
    UnknownDownloadError,
    details,
)
from reflektortts.events import DownloadEvent

logger = logging.getLogger(__name__)

PROGRESS_SECONDS = 0.25
"""How often a running download reports its progress."""


class State(StrEnum):
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    INSTALLED = "installed"


@dataclass(frozen=True)
class Listed:
    entry: Entry
    state: State
    done: int = 0
    total: int | None = None


@dataclass(frozen=True)
class Listing:
    entries: tuple[Listed, ...]
    errors: tuple[str, ...]
    """Why some source's list could not be shown, for the user."""


class Downloads:
    def __init__(self, sources: Mapping[str, DownloadSource], on_event: Callable[[DownloadEvent], None]) -> None:
        self._sources = sources
        self._on_event = on_event
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        """Refreshes one at a time, so two never fetch the same lists at once; listing what was
        saved never waits for a refresh."""
        self._entries: dict[str, Entry] = {}
        self._running: dict[str, tuple[int, int | None]] = {}
        """Bytes done and total of each running download, by entry ID."""

    def listing(self, refresh: bool) -> Listing:
        """Every source's entries; refresh fetches their lists from the internet. A source that
        fails is reported in errors, and the others are listed."""
        entries: list[Entry] = []
        errors: list[str] = []
        with self._refresh_lock if refresh else contextlib.nullcontext():
            for name, source in self._sources.items():
                try:
                    entries.extend(source.entries(refresh))
                except DownloadError as error:
                    logger.warning("Could not list the downloads from %s: %s", name, details(error))
                    errors.append(str(error))
                except Exception as error:
                    logger.exception("Download source %s failed", name)
                    errors.append(f"Could not list the downloads from {name}: {error}")
        with self._lock:
            self._entries = {entry.id: entry for entry in entries}
            listed = tuple(self._listed(entry) for entry in entries)
        return Listing(listed, tuple(errors))

    def start(self, entry_id: str) -> None:
        """Starts downloading an entry; raises DownloadError if it cannot."""
        entry = self._find(entry_id)
        with self._lock:
            if entry_id in self._running:
                raise DownloadStateError(f"{entry.name} is already downloading.")
            self._running[entry_id] = (0, entry.size)
        threading.Thread(target=self._download, args=(entry,), name=f"download {entry_id}", daemon=True).start()

    def remove(self, entry_id: str) -> None:
        entry = self._find(entry_id)
        with self._lock:
            if entry_id in self._running:
                raise DownloadStateError(f"{entry.name} is downloading: wait until it is done.")
        if not entry.installed:
            raise DownloadStateError(f"{entry.name} is not installed.")
        try:
            self._source(entry).remove(entry)
        except OSError as error:
            raise DownloadError(
                f"{entry.name} could not be removed ({error.strerror or error}). Close what is using it and try again."
            ) from error
        logger.info("Removed %s", entry.name)
        self._mark_installed(entry, False)
        self._on_event(DownloadEvent(entry_id, "removed"))

    def _find(self, entry_id: str) -> Entry:
        """The entry with this ID. Entries come from the last listing; if no client has listed
        them yet (or the ID is new), the saved lists are read once, without the internet if a list
        was saved before."""
        with self._lock:
            entry = self._entries.get(entry_id)
        if entry is None:
            self.listing(refresh=False)
            with self._lock:
                entry = self._entries.get(entry_id)
        if entry is None:
            raise UnknownDownloadError(f'There is no download "{entry_id}".')
        return entry

    def _mark_installed(self, entry: Entry, installed: bool) -> None:
        """Keeps the known entries current between listings."""
        with self._lock:
            if entry.id in self._entries:
                self._entries[entry.id] = replace(entry, installed=installed)

    def _listed(self, entry: Entry) -> Listed:
        if entry.id in self._running:
            done, total = self._running[entry.id]
            return Listed(entry, State.DOWNLOADING, done, total)
        return Listed(entry, State.INSTALLED if entry.installed else State.AVAILABLE)

    def _source(self, entry: Entry) -> DownloadSource:
        return self._sources[entry.id.split(":", 1)[0]]

    def _download(self, entry: Entry) -> None:
        last_report = 0.0

        def progress(done: int, total: int | None) -> None:
            nonlocal last_report
            with self._lock:
                self._running[entry.id] = (done, total)
            if time.monotonic() - last_report >= PROGRESS_SECONDS:
                last_report = time.monotonic()
                self._on_event(DownloadEvent(entry.id, "downloading", done, total))

        logger.info("Downloading %s", entry.name)
        try:
            self._source(entry).download(entry, progress)
        except Exception as error:
            if not isinstance(error, DownloadError):
                logger.exception("Downloading %s failed", entry.name)
            message = str(error)
            logger.warning("Could not download %s: %s", entry.name, message)
            with self._lock:
                self._running.pop(entry.id, None)
            self._on_event(DownloadEvent(entry.id, "failed", message=message))
            return
        with self._lock:
            done, total = self._running.pop(entry.id, (0, None))
        self._mark_installed(entry, True)
        logger.info("Installed %s", entry.name)
        self._on_event(DownloadEvent(entry.id, "installed", done, total))
