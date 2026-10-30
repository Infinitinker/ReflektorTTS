import threading
import time
from collections.abc import Callable, Iterator

import pytest

from reflektortts.events import SubtitleEvent, TextEvent
from reflektortts.sinks.subtitles import Subtitles, Timing

QUICK = Timing(min_seconds=0.05, characters_per_second=1e9, hold=0.05)
TIMEOUT = 2.0


class Published:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, event: SubtitleEvent) -> None:
        with self._lock:
            self.texts.append(event.text)


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def line(text: str) -> TextEvent:
    return TextEvent("messages", text, 0.0)


@pytest.fixture
def published() -> Published:
    return Published()


@pytest.fixture
def make_subtitles(published: Published) -> Iterator[Callable[..., Subtitles]]:
    made: list[Subtitles] = []

    def make(enabled: bool = True, timing: Timing = QUICK) -> Subtitles:
        made.append(Subtitles(published, enabled, timing))
        return made[-1]

    yield make
    for subtitles in made:
        subtitles.close()


def test_a_line_that_is_not_spoken_is_hidden_after_its_reading_time(
    make_subtitles: Callable[..., Subtitles], published: Published
) -> None:
    subtitles = make_subtitles()

    subtitles.deliver(line("Kill Frenzy!"))

    wait_until(lambda: published.texts == ["Kill Frenzy!", ""])


def test_a_spoken_line_stays_until_a_moment_after_the_voice_stops(
    make_subtitles: Callable[..., Subtitles], published: Published
) -> None:
    subtitles = make_subtitles()

    subtitles.deliver(line("Nice wheels."))
    subtitles.speaking(True)
    time.sleep(0.2)
    assert published.texts == ["Nice wheels."]
    subtitles.speaking(False)

    wait_until(lambda: published.texts == ["Nice wheels.", ""])


def test_a_new_line_replaces_the_one_shown(make_subtitles: Callable[..., Subtitles], published: Published) -> None:
    subtitles = make_subtitles()
    subtitles.speaking(True)

    subtitles.deliver(line("First."))
    subtitles.deliver(line("Second."))
    subtitles.speaking(False)

    wait_until(lambda: published.texts == ["First.", "Second.", ""])


def test_long_lines_stay_longer_than_short_ones() -> None:
    timing = Timing(min_seconds=2.0, characters_per_second=15.0, hold=1.0)
    published = Published()
    clock = [100.0]
    subtitles = Subtitles(published, True, timing, clock=lambda: clock[0])
    try:
        subtitles.deliver(line("x" * 60))
        clock[0] += 3.9
        time.sleep(0.05)
        assert published.texts == ["x" * 60]
    finally:
        subtitles.close()


def test_nothing_is_shown_while_switched_off_and_switching_off_hides_the_subtitle(
    make_subtitles: Callable[..., Subtitles], published: Published
) -> None:
    subtitles = make_subtitles(enabled=False)
    subtitles.deliver(line("Hidden."))
    assert published.texts == []

    subtitles.configure(True)
    subtitles.speaking(True)
    subtitles.deliver(line("Shown."))
    subtitles.configure(False)

    assert published.texts == ["Shown.", ""]


def test_close_hides_the_subtitle(published: Published) -> None:
    subtitles = Subtitles(published, True, QUICK)
    subtitles.speaking(True)
    subtitles.deliver(line("Bye."))

    subtitles.close()

    assert published.texts == ["Bye.", ""]
