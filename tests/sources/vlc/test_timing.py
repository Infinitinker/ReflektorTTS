"""Where playback is, to a fraction of a second, from VLC's status: playing, without a length, and paused."""

from dataclasses import replace

import pytest

from reflektortts.sources.vlc.timing import PlaybackClock
from reflektortts.sources.vlc.web import PlayerStatus

PLAYING = PlayerStatus(state="playing", time=8, position=0.0, length=120, rate=1.0, subtitle_delay=0.0, item=2)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(("position", "seconds"), [(8.5 / 120, 8.5), (7.9 / 120, 8.0), (9.5 / 120, 8.999)])
def test_position_times_length_is_kept_within_the_second_vlc_reports(position: float, seconds: float) -> None:
    assert PlaybackClock(Clock()).media_time(replace(PLAYING, position=position)) == pytest.approx(seconds)


def test_without_a_length_the_time_is_carried_on_at_the_playback_rate() -> None:
    clock = Clock()
    playback = PlaybackClock(clock)
    unknown = replace(PLAYING, length=-1, rate=2.0)

    assert playback.media_time(unknown) == 8.0
    clock.now += 0.2
    assert playback.media_time(unknown) == pytest.approx(8.4)
    clock.now += 1.0
    assert playback.media_time(unknown) == pytest.approx(8.999)
    assert playback.media_time(replace(unknown, time=9)) == 9.0


def test_while_paused_the_time_stands_still() -> None:
    clock = Clock()
    playback = PlaybackClock(clock)
    unknown = replace(PLAYING, length=0)
    playback.media_time(unknown)
    clock.now += 0.3
    playback.media_time(unknown)

    clock.now += 0.5
    assert playback.media_time(replace(unknown, state="paused")) == pytest.approx(8.3)
