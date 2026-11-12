"""VlcSource: the subtitle VLC shows now, read from the media's subtitle file at VLC's playback time."""

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reflektortts.languages import Languages
from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.formats import read_cues
from reflektortts.sources.vlc.formats.cues import Cues
from reflektortts.sources.vlc.subtitles import SubtitleFile, find_subtitles, legacy_encoding
from reflektortts.sources.vlc.timing import PlaybackClock
from reflektortts.sources.vlc.uri import uri_to_path
from reflektortts.sources.vlc.web import NotAnsweringError, PlayerStatus, VlcClient
from reflektortts.sources.vlc.web_settings import REACHABLE_HOSTS, SettingsFile, WebSettings

logger = logging.getLogger(__name__)

STARTUP_GRACE = 5.0
"""Seconds after the source starts in which VLC not answering is no error: it is starting."""
RETRY_AFTER = 2.0
"""Seconds before asking again a VLC that did not answer: each try may wait out the timeout."""
LOOKUP_RETRY = 3.0
"""Seconds before looking for subtitles again where there were none, e.g. until the user adds them."""

OFF = "VLC's web interface is off: close VLC, enable the VLC integration in the Profiles tab, then start VLC again."


@dataclass(frozen=True)
class _Subtitles:
    file: SubtitleFile
    stamp: int
    """The file's modification time when it was read: people fix subtitle timing while watching."""
    cues: Cues


@dataclass
class _Lookup:
    """The subtitles found for one item of the playlist, in one language."""

    key: tuple[int, str]
    media: Path | None = None
    subtitles: _Subtitles | None = None
    error: VlcError | None = None
    retry_at: float = 0.0


class VlcSource:
    def __init__(
        self,
        name: str,
        poll_interval: float,
        settings: SettingsFile,
        connect: Callable[[int, bytes], VlcClient] = VlcClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._settings = settings
        self._connect = connect
        self._clock = clock
        self._started = clock()
        self._client: VlcClient | None = None
        self._client_for: tuple[int, bytes] | None = None
        self._retry_at = 0.0
        self._unanswered: VlcError | None = None
        self._lookup: _Lookup | None = None
        self._playback = PlaybackClock(clock)

    def read(self, languages: Languages) -> str | None:
        client = self._client_of(self._settings.current())
        status = self._status(client)
        if status is None or status.state == "stopped" or status.item < 0:
            return None
        cues = self._cues(client, status.item, languages.input)
        if cues is None:
            return None
        # A positive delay shows subtitles later than their file says.
        return cues.at(self._playback.media_time(status) - status.subtitle_delay)

    def close(self) -> None:
        pass

    def _client_of(self, settings: WebSettings) -> VlcClient:
        if not settings.ready:
            raise VlcError(OFF)
        if settings.host.lower() not in REACHABLE_HOSTS:
            raise VlcError(
                f"VLC's web interface listens only on {settings.host}: "
                "set its host (http-host) to 127.0.0.1 in VLC's preferences, then restart VLC."
            )
        key = (settings.port, settings.password)
        if self._client is None or key != self._client_for:
            self._client, self._client_for = self._connect(*key), key
        return self._client

    def _status(self, client: VlcClient) -> PlayerStatus | None:
        """VLC's status; None while VLC starts. After VLC does not answer, it is not asked again
        for a moment, and the error stands meanwhile."""
        now = self._clock()
        if now < self._retry_at:
            if self._unanswered is not None:
                raise self._unanswered
            return None
        try:
            status = client.status()
        except NotAnsweringError as error:
            self._retry_at = now + RETRY_AFTER
            if now - self._started < STARTUP_GRACE:
                return None
            self._unanswered = error
            raise
        self._retry_at, self._unanswered = 0.0, None
        return status

    def _cues(self, client: VlcClient, item: int, language: str) -> Cues | None:
        """The subtitles of the item, looked up once per item and language and again a moment
        after they were not found; read again when their file changes."""
        now = self._clock()
        lookup = self._lookup
        if lookup is None or lookup.key != (item, language):
            lookup = self._lookup = _Lookup((item, language))
        elif lookup.subtitles is not None:
            return self._current(lookup, lookup.subtitles)
        elif now < lookup.retry_at:
            if lookup.error is not None:
                raise lookup.error
            return None
        lookup.retry_at = now + LOOKUP_RETRY
        try:
            if lookup.media is None:
                lookup.media = self._media(client, lookup)
            found = find_subtitles(lookup.media, language)
            if found is not None:
                lookup.subtitles = _load(found, language)
        except VlcError as error:
            lookup.error = error
            raise
        lookup.error = None
        return None if lookup.subtitles is None else lookup.subtitles.cues

    def _current(self, lookup: _Lookup, subtitles: _Subtitles) -> Cues | None:
        """The lookup's subtitles, read again if their file has changed; if it is gone, they are
        looked up again on the next read."""
        try:
            if subtitles.file.path.stat().st_mtime_ns != subtitles.stamp:
                subtitles = lookup.subtitles = _load(subtitles.file, lookup.key[1])
        except (OSError, VlcError) as error:
            logger.info("Looking for subtitles again: %s", error)
            self._lookup = _Lookup(lookup.key, media=lookup.media)
            return None
        return subtitles.cues

    def _media(self, client: VlcClient, lookup: _Lookup) -> Path:
        playing = client.playlist_item(lookup.key[0])
        if playing is None:
            raise VlcError("Cannot find what VLC is playing in its playlist: play it again from the playlist.")
        path = uri_to_path(playing.uri)
        if path is None:
            lookup.retry_at = math.inf  # It stays a stream until the item changes.
            raise VlcError(
                "VLC is playing a stream: subtitles are read only from files next to a video on this computer."
            )
        return path


def _load(file: SubtitleFile, language: str) -> _Subtitles:
    path = file.path
    try:
        stamp = path.stat().st_mtime_ns
        cues = read_cues(file.format, path.read_bytes(), legacy_encoding(language))
    except OSError as error:
        raise VlcError(f"Cannot read the subtitles in {path.name} ({error.strerror}).") from error
    if not cues:
        raise VlcError(f"No subtitles found in {path.name}: is it in the {file.format.name} format?")
    logger.info("Reading %d subtitles from %s", len(cues), path)
    return _Subtitles(file, stamp, cues)
