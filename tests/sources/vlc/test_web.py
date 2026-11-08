import base64
import http.client
import urllib.error
from email.message import Message

import pytest

from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.web import TIMEOUT, NotAnsweringError, PlayerStatus, PlaylistItem, VlcClient
from tests.sources.vlc.fake_vlc import FakeVlc, playlist


def client(vlc: FakeVlc, port: int = 8080) -> VlcClient:
    return VlcClient(port, "pässword".encode(), vlc)


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://127.0.0.1:8080/requests/status.json", code, "error", Message(), None)


def test_the_status_is_read_from_127_0_0_1_with_basic_auth_and_an_empty_user() -> None:
    vlc = FakeVlc()

    status = client(vlc, 9090).status()

    assert status == PlayerStatus(
        state="playing", time=8, position=0.070424996316433, length=120, rate=1.0, subtitle_delay=0.0, item=2
    )
    request = vlc.requests[0]
    assert request.full_url == "http://127.0.0.1:9090/requests/status.json"
    assert request.get_header("Authorization") == "Basic " + base64.b64encode(":pässword".encode()).decode()
    assert vlc.timeouts == [TIMEOUT]


def test_without_an_input_vlc_reports_no_item() -> None:
    vlc = FakeVlc()
    vlc.status |= {"state": "stopped", "currentplid": -1, "time": 0, "length": 0, "position": 0}

    assert client(vlc).status().item == -1


def test_the_playing_item_is_found_in_the_playlist_tree_by_its_id() -> None:
    vlc = FakeVlc()
    vlc.playlist = playlist((3, "file:///C:/a.mkv"), (7, "file:///C:/b.mkv"))

    assert client(vlc).playlist_item(7) == PlaylistItem("b.mkv", "file:///C:/b.mkv")
    assert client(vlc).playlist_item(5) is None
    assert vlc.paths() == ["/requests/playlist.json", "/requests/playlist.json"]


def test_an_unanswered_connection_says_vlc_does_not_answer() -> None:
    vlc = FakeVlc()
    vlc.failure = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))

    with pytest.raises(NotAnsweringError, match="does not answer on port 8080"):
        client(vlc).status()


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), http.client.RemoteDisconnected("closed")])
def test_a_timeout_or_a_dropped_connection_counts_as_not_answering(failure: Exception) -> None:
    vlc = FakeVlc()
    vlc.failure = failure

    with pytest.raises(NotAnsweringError):
        client(vlc).status()


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (401, "did not accept the web interface password: close VLC and start it again"),
        (403, "has its web interface off: close VLC and start it again"),
        (404, "has its web interface off"),
        (500, r"answered with an error \(HTTP 500\)"),
    ],
)
def test_refusals_say_what_to_do(code: int, message: str) -> None:
    vlc = FakeVlc()
    vlc.failure = http_error(code)

    with pytest.raises(VlcError, match=message):
        client(vlc).status()


@pytest.mark.parametrize("body", [b"<html>It works</html>", b"[]", b'{"apiversion": 3, "state": "playing"}'])
def test_something_that_is_not_vlcs_status_is_told_apart(body: bytes) -> None:
    vlc = FakeVlc()
    vlc.body = body

    with pytest.raises(VlcError, match="Another program answers on port 8080, not VLC"):
        client(vlc).status()


def test_another_vlc_version_is_refused() -> None:
    vlc = FakeVlc()
    vlc.status |= {"apiversion": 4, "version": "4.0.0 Otto Chriek"}

    with pytest.raises(VlcError, match=r"This VLC version \(4.0.0 Otto Chriek\) is not supported yet"):
        client(vlc).status()
