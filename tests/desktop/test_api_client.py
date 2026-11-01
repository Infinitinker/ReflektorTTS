import queue
from collections.abc import Iterator
from dataclasses import replace

import pytest

from reflektortts.api.server import ApiServer
from reflektortts.desktop.api_client import ApiClientError, StatusFeed, post, request_json
from reflektortts.desktop.catalog import DownloadProgress, PreviewState, parse_list
from reflektortts.desktop.status import CoreStatus
from reflektortts.events import DownloadEvent, PreviewEvent
from tests.api.test_server import GOSIA, FakeCore

TIMEOUT = 5


@pytest.fixture
def core() -> FakeCore:
    return FakeCore()


@pytest.fixture
def server(core: FakeCore) -> Iterator[ApiServer]:
    running = ApiServer(core, port=0)
    running.start()
    yield running
    running.stop()


def url(server: ApiServer) -> str:
    return f"http://127.0.0.1:{server.port}/v1"


def test_commands_reach_the_core(server: ApiServer, core: FakeCore) -> None:
    post("/pause", url(server))
    assert core.current.paused

    post("/resume", url(server))
    assert not core.current.paused


def test_a_core_that_does_not_answer_is_an_error() -> None:
    with pytest.raises(ApiClientError, match="did not respond"):
        post("/pause", "http://127.0.0.1:9/v1")


def test_requests_return_the_answer_or_the_cores_message(server: ApiServer, core: FakeCore) -> None:
    listing = parse_list(request_json("GET", "/downloads?refresh=1", base_url=url(server)))
    request_json("POST", "/downloads", {"id": GOSIA.id}, base_url=url(server))

    assert [item.id for item in listing.items] == [GOSIA.id]
    assert core.refreshed is True and core.started == [GOSIA.id]
    with pytest.raises(ApiClientError, match='There is no download "piper:x".'):
        request_json("POST", "/downloads", {"id": "piper:x"}, base_url=url(server))


def test_the_feed_passes_on_the_status_and_its_changes(server: ApiServer, core: FakeCore) -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, base_url=url(server))
    feed.start()
    try:
        assert statuses.get(timeout=TIMEOUT) == CoreStatus(game="Grand Theft Auto 2", paused=False)
        core.bus.publish(replace(core.current, game=None, paused=True))
        assert statuses.get(timeout=TIMEOUT) == CoreStatus(game=None, paused=True)
    finally:
        feed.stop()


def test_the_feed_passes_on_download_progress(server: ApiServer, core: FakeCore) -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    progress: queue.SimpleQueue[DownloadProgress] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, progress.put, base_url=url(server))
    feed.start()
    try:
        statuses.get(timeout=TIMEOUT)
        core.bus.publish(DownloadEvent(GOSIA.id, "failed", message="Check your internet connection."))
        assert progress.get(timeout=TIMEOUT) == DownloadProgress(
            GOSIA.id, "failed", 0, None, "Check your internet connection."
        )
    finally:
        feed.stop()


def test_the_feed_passes_on_previews(server: ApiServer, core: FakeCore) -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    previews: queue.SimpleQueue[PreviewState] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, on_preview=previews.put, base_url=url(server))
    feed.start()
    try:
        statuses.get(timeout=TIMEOUT)
        core.bus.publish(PreviewEvent("windows:Microsoft Adam", playing=True))
        assert previews.get(timeout=TIMEOUT) == PreviewState("windows:Microsoft Adam", playing=True)
    finally:
        feed.stop()


def test_the_feed_says_when_the_core_does_not_answer() -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, base_url="http://127.0.0.1:9/v1")
    feed.start()
    try:
        assert statuses.get(timeout=TIMEOUT) is None
    finally:
        feed.stop()
