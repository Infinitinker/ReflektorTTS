import sys

import pytest

from reflektortts.desktop.system.tray_host import tray_available

TRAY_OWNER = 0x400001
NONE = 0


class FakeDisplay:
    """An X display whose tray selection on screen 0 has the given owner."""

    def __init__(self, owner: int) -> None:
        self._owner = owner
        self.closed = False

    def get_default_screen(self) -> int:
        return 0

    def intern_atom(self, name: str) -> str:
        return name

    def get_selection_owner(self, atom: str) -> int:
        return self._owner if atom == "_NET_SYSTEM_TRAY_S0" else NONE

    def close(self) -> None:
        self.closed = True


def test_windows_always_has_a_tray(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    assert tray_available()


@pytest.mark.parametrize(("owner", "expected"), [(TRAY_OWNER, True), (NONE, False)])
def test_on_linux_a_tray_owns_the_tray_selection(monkeypatch: pytest.MonkeyPatch, owner: int, expected: bool) -> None:
    xlib = pytest.importorskip("Xlib.display", reason="python-xlib is installed only on Linux")
    display = FakeDisplay(owner)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(xlib, "Display", lambda: display)

    assert tray_available() is expected
    assert display.closed
