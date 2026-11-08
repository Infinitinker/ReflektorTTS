import sys

import pytest

from reflektortts.desktop import win32_windows
from reflektortts.desktop.dock import PANEL_WIDTH, Dock, dock_beside, dock_of, screen_of
from reflektortts.desktop.screen import Rect, Screen

WORK_AREA = Rect(0, 0, 2560, 1392)


def test_it_opens_on_the_right_when_it_fits_there() -> None:
    screen = Screen(frame=Rect(100, 50, 900, 690), work_area=WORK_AREA, scale=1.0)

    assert dock_beside(screen) == Dock("right", 900, 50, 640)


def test_it_opens_on_the_left_when_the_right_has_no_room() -> None:
    right = WORK_AREA.right - PANEL_WIDTH + 1
    screen = Screen(frame=Rect(right - 800, 50, right, 690), work_area=WORK_AREA, scale=1.0)

    assert dock_beside(screen) == Dock("left", right - 800, 50, 640)


def test_its_width_follows_the_display_scale() -> None:
    # Fits at 100%, not at 150%.
    right = WORK_AREA.right - PANEL_WIDTH - 10
    frame = Rect(right - 1200, 75, right, 1035)

    assert dock_beside(Screen(frame, WORK_AREA, 1.0)).side == "right"
    assert dock_beside(Screen(frame, WORK_AREA, 1.5)) == Dock("left", right - 1200, 75, 960)


def test_without_room_on_either_side_it_opens_over_the_window_at_the_display_edge() -> None:
    screen = Screen(frame=Rect(0, 0, 2560, 1392), work_area=WORK_AREA, scale=1.0)

    assert dock_beside(screen) == Dock("left", 2560, 0, 1392)


def test_on_a_second_display_its_own_work_area_counts() -> None:
    work_area = Rect(2560, -197, 3640, 1675)
    screen = Screen(frame=Rect(3000, 0, 3600, 640), work_area=work_area, scale=1.0)

    assert dock_beside(screen) == Dock("left", 3000, 0, 640)


def test_the_arguments_say_where_it_opens() -> None:
    assert Dock("right", -1200, -30, 640).arguments() == [
        "--dock-side",
        "right",
        "--dock-x",
        "-1200",
        "--dock-y",
        "-30",
        "--dock-height",
        "640",
    ]


class FakeRoot:
    def winfo_id(self) -> int:
        return 42

    def winfo_rootx(self) -> int:
        return 10

    def winfo_rooty(self) -> int:
        return 40

    def winfo_width(self) -> int:
        return 800

    def winfo_height(self) -> int:
        return 600

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def winfo_fpixels(self, distance: str) -> float:
        assert distance == "1i"
        return 144.0


def test_off_windows_tk_measures_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    screen = screen_of(FakeRoot())  # type: ignore[arg-type]

    assert screen == Screen(frame=Rect(10, 40, 810, 640), work_area=Rect(0, 0, 1920, 1080), scale=1.5)


def test_on_windows_windows_measures_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    measured = Screen(frame=Rect(100, 50, 900, 690), work_area=WORK_AREA, scale=1.0)
    asked: list[int] = []

    def window_screen(widget: int) -> Screen:
        asked.append(widget)
        return measured

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(win32_windows, "window_screen", window_screen)

    assert screen_of(FakeRoot()) == measured  # type: ignore[arg-type]
    assert dock_of(FakeRoot()) == Dock("right", 900, 50, 640)  # type: ignore[arg-type]
    assert asked == [42, 42]


def test_where_windows_cannot_tell_it_opens_centered(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tk's measures on Windows are scaled down for DPI, so they are not used instead.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(win32_windows, "window_screen", lambda widget: None)

    assert screen_of(FakeRoot()) is None  # type: ignore[arg-type]
    assert dock_of(FakeRoot()) is None  # type: ignore[arg-type]
