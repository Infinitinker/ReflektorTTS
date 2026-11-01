import pytest

from reflektortts.desktop.status import CoreStatus
from reflektortts.desktop.theme import BUSY, DIM, GOOD
from reflektortts.desktop.window import status_color


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
