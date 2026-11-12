"""The downloads: several at once, their state and errors, and removing what is installed."""

import queue
import threading

import pytest

from reflektortts.downloads.manager import Downloads, Listed, State
from reflektortts.downloads.source import DownloadError, DownloadStateError, Entry, Kind, Progress, UnknownDownloadError
from reflektortts.events import DownloadEvent

TIMEOUT = 5


def entry(entry_id: str, installed: bool = False) -> Entry:
    return Entry(
        entry_id, Kind.VOICE, entry_id.split(":")[1], ("pl",), 100, None, "https://example.invalid", installed, "Fake"
    )


class FakeSource:
    """Downloads only when released, so tests see them running."""

    def __init__(self, *entries: Entry, failing: bool = False) -> None:
        self.listed = list(entries)
        self.failing = failing
        self.release = threading.Event()
        self.removed: list[str] = []

    def entries(self, refresh: bool) -> list[Entry]:
        if self.failing:
            raise DownloadError(
                "Could not reach the voice list. Check your internet connection, then close and open the window again."
            )
        return self.listed

    def download(self, entry: Entry, progress: Progress) -> None:
        progress(50, 100)
        self.release.wait(TIMEOUT)
        if entry.id.endswith("broken"):
            raise DownloadError("The downloaded voice is damaged. Try again.")
        progress(100, 100)

    def remove(self, entry: Entry) -> None:
        if entry.id.endswith("locked"):
            raise PermissionError(13, "Access is denied")
        self.removed.append(entry.id)


def until(events: "queue.SimpleQueue[DownloadEvent]", state: str) -> DownloadEvent:
    while (event := events.get(timeout=TIMEOUT)).state != state:
        pass
    return event


def test_several_downloads_run_at_once_and_report_when_installed() -> None:
    events: queue.SimpleQueue[DownloadEvent] = queue.SimpleQueue()
    source = FakeSource(entry("fake:a"), entry("fake:b"))
    downloads = Downloads({"fake": source}, events.put)
    downloads.listing(refresh=True)

    downloads.start("fake:a")
    downloads.start("fake:b")
    assert until(events, "downloading").done == 50
    states = {listed.entry.id: listed.state for listed in downloads.listing(refresh=False).entries}
    assert states == {"fake:a": State.DOWNLOADING, "fake:b": State.DOWNLOADING}
    source.release.set()

    installed = {until(events, "installed").entry_id, until(events, "installed").entry_id}
    assert installed == {"fake:a", "fake:b"}


def test_a_failed_download_says_why() -> None:
    events: queue.SimpleQueue[DownloadEvent] = queue.SimpleQueue()
    source = FakeSource(entry("fake:broken"))
    source.release.set()
    downloads = Downloads({"fake": source}, events.put)
    downloads.listing(refresh=True)

    downloads.start("fake:broken")

    assert until(events, "failed").message == "The downloaded voice is damaged. Try again."


def test_a_source_that_cannot_list_is_reported_and_the_others_are_listed() -> None:
    sources = {"fake": FakeSource(entry("fake:a", installed=True)), "down": FakeSource(failing=True)}
    downloads = Downloads(sources, lambda event: None)

    listing = downloads.listing(refresh=True)

    assert listing.entries == (Listed(entry("fake:a", installed=True), State.INSTALLED),)
    assert listing.errors == (
        "Could not reach the voice list. Check your internet connection, then close and open the window again.",
    )


def test_unknown_or_running_downloads_cannot_start_or_be_removed() -> None:
    source = FakeSource(entry("fake:a"))
    downloads = Downloads({"fake": source}, lambda event: None)
    downloads.listing(refresh=True)

    with pytest.raises(DownloadError, match='no download "fake:x"'):
        downloads.start("fake:x")
    downloads.start("fake:a")
    with pytest.raises(DownloadError, match="already downloading"):
        downloads.start("fake:a")
    with pytest.raises(DownloadError, match="is downloading"):
        downloads.remove("fake:a")
    source.release.set()


def test_removing_reports_it() -> None:
    events: list[DownloadEvent] = []
    source = FakeSource(entry("fake:a", installed=True))
    downloads = Downloads({"fake": source}, events.append)
    downloads.listing(refresh=True)

    downloads.remove("fake:a")

    assert source.removed == ["fake:a"]
    assert events == [DownloadEvent("fake:a", "removed")]


def test_a_file_that_cannot_be_removed_is_reported() -> None:
    events: list[DownloadEvent] = []
    downloads = Downloads({"fake": FakeSource(entry("fake:locked", installed=True))}, events.append)
    downloads.listing(refresh=True)

    with pytest.raises(DownloadError, match=r"locked could not be removed \(Access is denied\)\. Close what"):
        downloads.remove("fake:locked")

    assert events == []


def test_downloads_can_start_and_be_removed_without_listing_them_first() -> None:
    events: queue.SimpleQueue[DownloadEvent] = queue.SimpleQueue()
    source = FakeSource(entry("fake:a"), entry("fake:b", installed=True))
    downloads = Downloads({"fake": source}, events.put)

    downloads.start("fake:a")
    downloads.remove("fake:b")
    source.release.set()

    assert until(events, "installed").entry_id == "fake:a"
    assert source.removed == ["fake:b"]


def test_what_is_not_installed_cannot_be_removed_and_a_download_counts_as_installed() -> None:
    events: queue.SimpleQueue[DownloadEvent] = queue.SimpleQueue()
    source = FakeSource(entry("fake:a"))
    downloads = Downloads({"fake": source}, events.put)
    downloads.listing(refresh=True)

    with pytest.raises(DownloadStateError, match="a is not installed"):
        downloads.remove("fake:a")
    with pytest.raises(UnknownDownloadError):
        downloads.remove("fake:x")
    downloads.start("fake:a")
    source.release.set()
    until(events, "installed")
    downloads.remove("fake:a")

    assert source.removed == ["fake:a"]
