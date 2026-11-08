import pytest

from reflektortts.desktop.status import CoreStatus
from reflektortts.desktop.theme import BUSY, DIM, GOOD
from reflektortts.desktop.window import hint_color, status_color


@pytest.mark.parametrize(
    ("status", "color"),
    [
        (None, DIM),
        (CoreStatus(app=None, paused=False), ""),
        (CoreStatus(app="GTA2", paused=False), GOOD),
        (CoreStatus(app="GTA2", paused=True), BUSY),
    ],
)
def test_the_status_color(status: CoreStatus | None, color: str) -> None:
    assert status_color(status) == color


@pytest.mark.parametrize(
    ("status", "color"),
    [
        (None, DIM),
        (CoreStatus(app="VLC", paused=False), DIM),
        (CoreStatus(app="VLC", paused=False, source_error="Off."), BUSY),
        (CoreStatus(app=None, paused=False, source_error="Off."), DIM),
    ],
)
def test_the_hint_is_amber_while_it_gives_a_source_s_error(status: CoreStatus | None, color: str) -> None:
    assert hint_color(status) == color
