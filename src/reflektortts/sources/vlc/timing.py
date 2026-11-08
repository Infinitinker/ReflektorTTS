"""Where playback is, to a fraction of a second, from VLC's status.

VLC 3 reports the time in whole seconds, rounded down, but its position (a fraction of the length)
several times a second. Position times length is clamped into the second the time names, since the
length is rounded down too. Without a length (some streams and files), the time is carried on from
the moment it last changed, at the playback rate, while VLC plays.
"""

import time
from collections.abc import Callable

from reflektortts.sources.vlc.web import PlayerStatus

WITHIN_SECOND = 0.999


class PlaybackClock:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._tick: tuple[int, int] | None = None
        """The item and the whole second the extra time is counted from."""
        self._extra = 0.0
        self._last = 0.0

    def media_time(self, status: PlayerStatus) -> float:
        """Seconds into the media."""
        if status.length > 0:
            self._tick = None
            return min(max(status.position * status.length, status.time), status.time + WITHIN_SECOND)
        now = self._clock()
        tick = (status.item, status.time)
        if tick != self._tick:
            self._tick, self._extra = tick, 0.0
        elif status.state == "playing":
            self._extra += (now - self._last) * status.rate
        self._last = now
        return status.time + min(self._extra, WITHIN_SECOND)
