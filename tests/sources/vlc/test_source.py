"""VlcSource: the cue at VLC's playback time, VLC not answering or its web interface off, and the subtitle file."""

import os
import urllib.error
from pathlib import Path

import pytest

from reflektortts.languages import Languages
from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.source import LOOKUP_RETRY, OFF, RETRY_AFTER, STARTUP_GRACE, VlcSource
from reflektortts.sources.vlc.web import NotAnsweringError, VlcClient
from reflektortts.sources.vlc.web_settings import SettingsFile
from tests.sources.vlc.fake_vlc import FakeVlc, playlist
from tests.sources.vlc.fake_vlcrc import FRESH, with_lines

ENGLISH = Languages("en", "pl")
POLISH = Languages("pl", "pl")
READY = with_lines(FRESH, "extraintf=http", "http-password=secret", "http-host=127.0.0.1")
SRT = b"1\n00:00:06,000 --> 00:00:07,000\nEarlier.\n\n2\n00:00:08,000 --> 00:00:09,000\nHello there.\n"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Setup:
    def __init__(self, tmp_path: Path) -> None:
        self.vlcrc = tmp_path / "vlcrc"
        self.vlcrc.write_bytes(READY)
        self.media = tmp_path / "Films ąę #1" / "movie.mkv"
        self.media.parent.mkdir()
        self.media.write_bytes(b"")
        self.vlc = FakeVlc()
        self.vlc.playlist = playlist((2, self.media.as_uri()))
        self.vlc.status |= {"time": 8, "position": 8.5 / 120}
        self.clock = Clock()
        self.connections: list[tuple[int, bytes]] = []
        self.source = VlcSource("subtitles", 0.2, SettingsFile(self.vlcrc), self.connect, self.clock)

    def connect(self, port: int, password: bytes) -> VlcClient:
        self.connections.append((port, password))
        return VlcClient(port, password, self.vlc)

    def subtitles(self, name: str, data: bytes = SRT) -> Path:
        path = self.media.parent / name
        path.write_bytes(data)
        return path

    def read(self, languages: Languages = ENGLISH) -> str | None:
        return self.source.read(languages)


@pytest.fixture
def vlc(tmp_path: Path) -> Setup:
    return Setup(tmp_path)


def test_the_cue_at_vlcs_playback_time_is_read(vlc: Setup) -> None:
    vlc.subtitles("movie.en.srt")

    assert vlc.read() == "Hello there."
    assert vlc.connections == [(8080, b"secret")]


def test_a_subtitle_delay_shows_earlier_cues_later(vlc: Setup) -> None:
    vlc.subtitles("movie.srt")
    vlc.vlc.status["subtitledelay"] = 2.0

    assert vlc.read() == "Earlier."


def test_between_cues_and_when_stopped_there_is_no_text(vlc: Setup) -> None:
    vlc.subtitles("movie.srt")
    vlc.vlc.status |= {"time": 7, "position": 7.5 / 120}
    assert vlc.read() is None

    vlc.vlc.status |= {"state": "stopped", "currentplid": -1, "time": 0, "position": 0, "length": 0}
    vlc.vlc.requests.clear()
    assert vlc.read() is None
    assert vlc.vlc.paths() == ["/requests/status.json"]


def test_while_paused_the_cue_stays(vlc: Setup) -> None:
    vlc.subtitles("movie.srt")
    vlc.vlc.status["state"] = "paused"

    assert vlc.read() == "Hello there."


def test_the_playlist_is_asked_only_when_the_item_or_the_language_changes(vlc: Setup) -> None:
    vlc.subtitles("movie.en.srt")
    vlc.subtitles("movie.pl.srt", SRT.replace(b"Hello there.", b"Dzie\xc5\x84 dobry."))
    other = vlc.subtitles("other.mkv", b"")
    vlc.subtitles("other.srt", SRT.replace(b"Hello there.", b"Other."))
    vlc.vlc.playlist = playlist((2, vlc.media.as_uri()), (3, other.as_uri()))

    assert [vlc.read(), vlc.read()] == ["Hello there.", "Hello there."]
    assert vlc.read(POLISH) == "Dzień dobry."
    vlc.vlc.status["currentplid"] = 3
    assert vlc.read() == "Other."
    assert vlc.vlc.paths().count("/requests/playlist.json") == 3


def test_vlc_not_answering_is_no_error_while_it_starts(vlc: Setup) -> None:
    vlc.vlc.failure = urllib.error.URLError(ConnectionRefusedError())

    assert vlc.read() is None
    vlc.clock.now += STARTUP_GRACE + 0.1
    with pytest.raises(NotAnsweringError, match="does not answer on port 8080"):
        vlc.read()


def test_vlc_not_answering_is_asked_again_only_after_a_moment(vlc: Setup) -> None:
    vlc.subtitles("movie.srt")
    vlc.clock.now += STARTUP_GRACE
    vlc.vlc.failure = urllib.error.URLError(ConnectionRefusedError())
    with pytest.raises(NotAnsweringError):
        vlc.read()

    vlc.vlc.failure = None
    with pytest.raises(NotAnsweringError):
        vlc.read()
    assert len(vlc.vlc.requests) == 1

    vlc.clock.now += RETRY_AFTER
    assert vlc.read() == "Hello there."


def test_with_the_web_interface_off_the_user_is_told_the_steps_in_order(vlc: Setup) -> None:
    vlc.vlcrc.write_bytes(with_lines(FRESH, "extraintf=http"))

    with pytest.raises(VlcError) as raised:
        vlc.read()

    assert str(raised.value) == OFF
    assert OFF.index("close VLC") < OFF.index("enable the VLC integration") < OFF.index("start VLC again")


def test_a_web_interface_on_another_host_is_named(vlc: Setup) -> None:
    vlc.vlcrc.write_bytes(READY.replace(b"http-host=127.0.0.1", b"http-host=192.168.1.2"))

    with pytest.raises(VlcError, match="listens only on 192.168.1.2"):
        vlc.read()


def test_a_new_password_or_port_connects_again(vlc: Setup) -> None:
    vlc.subtitles("movie.srt")
    vlc.read()
    vlc.vlcrc.write_bytes(with_lines(READY, "http-port=9090"))
    os.utime(vlc.vlcrc, ns=(1, 1))

    vlc.read()

    assert vlc.connections == [(8080, b"secret"), (9090, b"secret")]


def test_without_any_subtitle_file_nothing_is_read_quietly(vlc: Setup) -> None:
    assert vlc.read() is None


def test_missing_subtitles_are_looked_for_again_after_a_moment(vlc: Setup) -> None:
    vlc.subtitles("movie.de.srt")
    with pytest.raises(VlcError, match="No English subtitles found: put movie.en.srt or movie.srt next to movie.mkv"):
        vlc.read()
    vlc.subtitles("movie.en.srt")

    with pytest.raises(VlcError, match="No English subtitles"):
        vlc.read()
    vlc.clock.now += LOOKUP_RETRY

    assert vlc.read() == "Hello there."


def test_subtitles_are_read_again_when_their_file_changes(vlc: Setup) -> None:
    path = vlc.subtitles("movie.srt")
    assert vlc.read() == "Hello there."

    path.write_bytes(SRT.replace(b"Hello there.", b"Fixed."))
    os.utime(path, ns=(1, 1))

    assert vlc.read() == "Fixed."


def test_a_stream_is_named_and_not_looked_up_again(vlc: Setup) -> None:
    vlc.vlc.playlist = playlist((2, "http://radio.example/stream.mp3"))

    for _ in range(2):
        vlc.clock.now += LOOKUP_RETRY
        with pytest.raises(VlcError, match="VLC is playing a stream: subtitles are read only from files"):
            vlc.read()

    assert vlc.vlc.paths().count("/requests/playlist.json") == 1


def test_an_item_missing_from_the_playlist_is_reported(vlc: Setup) -> None:
    vlc.vlc.status["currentplid"] = 9

    with pytest.raises(VlcError, match="Cannot find what VLC is playing in its playlist"):
        vlc.read()


def test_a_subtitle_file_without_cues_is_reported_with_its_format(vlc: Setup) -> None:
    vlc.subtitles("movie.srt", b"WEBVTT\n\nnot srt\n")

    with pytest.raises(VlcError) as raised:
        vlc.read()

    assert str(raised.value) == "No subtitles found in movie.srt: is it in the SubRip (.srt) format?"


def test_subtitles_in_other_formats_are_read_too(vlc: Setup) -> None:
    vlc.subtitles("movie.en.vtt", b"WEBVTT\n\n00:00:08.000 --> 00:00:09.000\n<v Anna>Hello &amp; welcome.\n")

    assert vlc.read() == "Hello & welcome."
