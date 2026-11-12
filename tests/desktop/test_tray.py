"""The desktop app's tray icon: its title, cut short and in Latin-1 where needed, notifying and stopping."""

from typing import Any

import pystray
import pytest

from reflektortts.desktop.tray import MAX_TITLE, Tray, latin1


class FakeIcon:
    """pystray's icon as Windows has it: any title, and notifications."""

    HAS_NOTIFICATION = True
    LATIN1 = False

    def __init__(self, name: str, icon: Any, title: str, menu: Any) -> None:
        self._title = title
        self.notified: list[tuple[str, str]] = []
        self.stopped = False

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        if self.LATIN1:
            value.encode("latin-1")

    def update_menu(self) -> None:
        pass

    def notify(self, message: str, title: str) -> None:
        self.notified.append((title, message))

    def run(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True


class X11Icon(FakeIcon):
    """pystray's X11 icon, the one used on Linux: it stores the title, then fails to name its window
    with it in Latin-1; and it shows no notifications."""

    HAS_NOTIFICATION = False
    LATIN1 = True


def tray(monkeypatch: pytest.MonkeyPatch, icon: type[FakeIcon] = FakeIcon) -> Tray:
    monkeypatch.setattr(pystray, "Icon", icon)
    return Tray(lambda: None, lambda: None, lambda: None, lambda: None, lambda: None)


def title(tray: Tray) -> str:
    return str(tray._icon.title)


def test_the_title_says_what_reflektortts_does(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = tray(monkeypatch)

    shown.show_status("Waiting for an app…", paused=False, connected=True)

    assert title(shown) == "ReflektorTTS: Waiting for an app…"


def test_a_long_title_is_cut_short_as_windows_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = tray(monkeypatch)

    shown.show_status("Reading " + "a" * 200, paused=False, connected=True)

    assert len(title(shown)) == MAX_TITLE
    assert title(shown).endswith("a…")


@pytest.mark.parametrize(
    ("status", "expected"),
    [("Starting…", "ReflektorTTS: Starting..."), ("Reading Wiedźmin", "ReflektorTTS: Reading Wied?min")],
)
def test_the_x11_icon_gets_its_title_in_latin_1(monkeypatch: pytest.MonkeyPatch, status: str, expected: str) -> None:
    shown = tray(monkeypatch, X11Icon)

    shown.show_status(status, paused=False, connected=True)

    assert title(shown) == expected


def test_whether_it_can_notify_follows_the_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tray(monkeypatch).can_notify
    assert not tray(monkeypatch, X11Icon).can_notify


def test_an_icon_never_started_needs_no_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = tray(monkeypatch)

    shown.stop()

    assert not shown._icon.stopped


def test_latin1_keeps_what_latin_1_has() -> None:
    assert latin1("Café à la carte") == "Café à la carte"
    assert latin1("Gdańsk…") == "Gda?sk..."
