import pytest

from reflektortts.desktop.status import CoreStatus
from reflektortts.desktop.theme import BUSY, DIM, GOOD
from reflektortts.desktop.window import app_settings_hint, hint_color, read_app, status_color


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


READ = CoreStatus(app="GTA2", paused=False, profile="gta2")


@pytest.mark.parametrize(
    ("status", "missing", "app"),
    [
        (READ, None, ("gta2", "GTA2")),
        (CoreStatus(app="GTA2", paused=True, profile="gta2"), None, ("gta2", "GTA2")),
        (READ, "No settings window.", None),
        (CoreStatus(app=None, paused=False), None, None),
        (CoreStatus(app="GTA2", paused=False), None, None),
        (None, None, None),
    ],
)
def test_app_settings_opens_the_app_being_read(
    status: CoreStatus | None, missing: str | None, app: tuple[str, str] | None
) -> None:
    assert read_app(status, missing) == app


def test_the_app_settings_hint_names_the_app_or_says_why_it_does_nothing() -> None:
    assert app_settings_hint(READ, None) == "Change the voice, languages and the rest for GTA2, in a window of its own."
    assert app_settings_hint(READ, "No settings window.") == "No settings window."
    assert app_settings_hint(CoreStatus(app=None, paused=False), None).endswith("select it in the Profiles tab.")
