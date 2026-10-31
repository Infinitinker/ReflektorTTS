import queue
from collections.abc import Iterator
from dataclasses import replace

import pytest

from reflektortts.api.server import ApiServer
from reflektortts.desktop.api_client import ApiClientError, StatusFeed, post
from reflektortts.desktop.status import CoreStatus
from tests.api.test_server import FakeCore

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


def test_the_feed_passes_on_the_status_and_its_changes(server: ApiServer, core: FakeCore) -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, url(server))
    feed.start()
    try:
        assert statuses.get(timeout=TIMEOUT) == CoreStatus(game="Grand Theft Auto 2", paused=False)
        core.bus.publish(replace(core.current, game=None, paused=True))
        assert statuses.get(timeout=TIMEOUT) == CoreStatus(game=None, paused=True)
    finally:
        feed.stop()


def test_the_feed_says_when_the_core_does_not_answer() -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, "http://127.0.0.1:9/v1")
    feed.start()
    try:
        assert statuses.get(timeout=TIMEOUT) is None
    finally:
        feed.stop()
