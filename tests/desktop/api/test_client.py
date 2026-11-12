"""The desktop app's API client: commands, answers, and the status feed, against a real API server."""

import http.server
import queue
import socket
import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from reflektortts.api.server import ApiServer
from reflektortts.desktop.api.catalog import DownloadProgress, PreviewState, parse_list
from reflektortts.desktop.api.client import (
    NO_ANSWER,
    ApiClientError,
    StatusFeed,
    post,
    reflektortts_answers,
    request_json,
)
from reflektortts.desktop.api.status import CoreStatus
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


def test_a_core_that_does_not_answer_is_an_error_that_says_what_to_do(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ApiClientError) as raised:
        post("/pause", "http://127.0.0.1:9/v1")

    assert str(raised.value) == NO_ANSWER
    assert "POST /pause got no answer" in caplog.text


def test_requests_return_the_answer_or_the_cores_message(server: ApiServer, core: FakeCore) -> None:
    listing = parse_list(request_json("POST", "/downloads/refresh", base_url=url(server)))
    request_json("POST", "/downloads", {"id": GOSIA.id}, base_url=url(server))

    assert [item.id for item in listing.items] == [GOSIA.id]
    assert core.refreshed is True and core.started == [GOSIA.id]
    with pytest.raises(ApiClientError, match='There is no download "piper:x".'):
        request_json("POST", "/downloads", {"id": "piper:x"}, base_url=url(server))


def test_reflektortts_answers_only_where_its_core_runs(server: ApiServer) -> None:
    assert reflektortts_answers(url(server))
    assert not reflektortts_answers("http://127.0.0.1:9/v1")


@pytest.mark.parametrize("answer", [b"<html>Another program</html>", b"[]", b'{"type": "other"}'])
def test_another_program_on_the_port_is_not_reflektortts(answer: bytes) -> None:
    class Other(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    with http.server.HTTPServer(("127.0.0.1", 0), Other) as other:
        thread = threading.Thread(target=other.serve_forever, daemon=True)
        thread.start()
        try:
            assert not reflektortts_answers(f"http://127.0.0.1:{other.server_port}/v1")
        finally:
            other.shutdown()


def test_a_program_that_does_not_speak_http_is_not_reflektortts() -> None:
    with socket.create_server(("127.0.0.1", 0)) as listener:

        def answer_garbage() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.recv(1024)
                connection.sendall(b"garbage\r\n\r\n")

        threading.Thread(target=answer_garbage, daemon=True).start()
        assert not reflektortts_answers(f"http://127.0.0.1:{listener.getsockname()[1]}/v1")


def test_the_feed_passes_on_the_status_and_its_changes(server: ApiServer, core: FakeCore) -> None:
    statuses: queue.SimpleQueue[CoreStatus | None] = queue.SimpleQueue()
    feed = StatusFeed(statuses.put, base_url=url(server))
    feed.start()
    try:
        first = statuses.get(timeout=TIMEOUT)
        assert first is not None
        assert (first.app, first.paused, first.voice) == ("Grand Theft Auto 2", False, core.current.voice)
        core.bus.publish(replace(core.current, app=None, paused=True))
        changed = statuses.get(timeout=TIMEOUT)
        assert changed is not None
        assert (changed.app, changed.paused) == (None, True)
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


def test_an_event_the_window_cannot_read_is_skipped() -> None:
    previews: list[PreviewState] = []
    feed = StatusFeed(lambda status: None, on_preview=previews.append)

    unreadable = ["not json", "[]", '{"type": "preview"}']
    for message in [*unreadable, '{"type": "preview", "voice": "piper:a", "playing": true}']:
        feed._handle(message)

    assert previews == [PreviewState("piper:a", playing=True)]


def test_commands_go_straight_to_the_core_past_a_proxy(
    server: ApiServer, core: FakeCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")

    post("/pause", url(server))

    assert core.current.paused
