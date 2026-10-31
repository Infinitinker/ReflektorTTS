import pytest

from reflektortts.desktop.status import CoreStatus, describe, parse_status


def test_a_status_event_gives_the_game_and_whether_reading_is_paused() -> None:
    event = {"type": "status", "game": {"title": "Mad Max", "pid": 42}, "paused": True, "voice": "piper:a"}

    assert parse_status(event) == CoreStatus(game="Mad Max", paused=True)
    assert parse_status({"type": "status", "game": None, "paused": False}) == CoreStatus(game=None, paused=False)


def test_other_events_are_not_a_status() -> None:
    assert parse_status({"type": "line", "source": "subtitles", "text": "Hi"}) is None


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (None, "Starting…"),
        (CoreStatus(game=None, paused=False), "Waiting for a game"),
        (CoreStatus(game="Mad Max", paused=False), "Reading Mad Max"),
        (CoreStatus(game="Mad Max", paused=True), "Reading Mad Max (paused)"),
    ],
)
def test_the_status_in_a_few_words(status: CoreStatus | None, text: str) -> None:
    assert describe(status) == text
