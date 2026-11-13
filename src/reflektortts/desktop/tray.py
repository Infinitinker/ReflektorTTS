"""The desktop app's icon next to the clock, with its menu. pystray runs it on a thread of its own,
so the menu's actions are called on that thread."""

import threading
from collections.abc import Callable

import pystray

from reflektortts.desktop.icon import icon_image

TRAY_ICON_SIZE = 32
"""The largest size a tray shows; the icon's simple drawing, which stays clear when scaled down."""
MAX_TITLE = 127
"""The longest tooltip Windows takes (128 characters with the ending zero); a longer one fails."""


class Tray:
    """start_with_windows tells whether ReflektorTTS starts with Windows, or None if it cannot; the
    menu then has no such item."""

    def __init__(
        self,
        on_open: Callable[[], None],
        on_pause_toggle: Callable[[], None],
        on_quit: Callable[[], None],
        start_with_windows: Callable[[], bool | None],
        on_start_with_windows_toggle: Callable[[], None],
    ) -> None:
        self._paused = False
        self._connected = False
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda: on_open(), default=True),
            pystray.MenuItem(
                lambda item: "Resume reading" if self._paused else "Pause reading",
                lambda: on_pause_toggle(),
                enabled=lambda item: self._connected,
            ),
            pystray.MenuItem(
                "Start with Windows",
                lambda: on_start_with_windows_toggle(),
                checked=lambda item: bool(start_with_windows()),
                visible=start_with_windows() is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: on_quit()),
        )
        self._icon = pystray.Icon("ReflektorTTS", icon_image(TRAY_ICON_SIZE), "ReflektorTTS", menu)
        self._thread = threading.Thread(target=self._icon.run, name="tray", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """Takes the icon away; nothing to do if it was never started (on a desktop without a tray)."""
        if self._thread.ident is None:
            return
        self._icon.stop()
        self._thread.join()

    def show_status(self, text: str, paused: bool, connected: bool) -> None:
        self._paused = paused
        self._connected = connected
        title = f"ReflektorTTS: {text}"
        if len(title) > MAX_TITLE:
            title = title[: MAX_TITLE - 1] + "…"
        try:
            self._icon.title = title
        except UnicodeEncodeError:
            # pystray's X11 icon, the one used on Linux, names its window in Latin-1, which has
            # neither "…" nor most letters outside Western Europe.
            self._icon.title = latin1(title)
        self._icon.update_menu()

    def refresh(self) -> None:
        """Shows the menu's checkmarks as they are now; Windows keeps the menu as it was last built."""
        self._icon.update_menu()

    @property
    def can_notify(self) -> bool:
        """pystray's X11 icon, the one used on Linux, shows no notifications."""
        return bool(self._icon.HAS_NOTIFICATION)

    def notify(self, title: str, message: str) -> None:
        """Windows puts the app's name above the title, so the title says something of its own."""
        self._icon.notify(message, title)


def latin1(text: str) -> str:
    """The text with "…" spelled out and the other characters Latin-1 does not have as "?"."""
    return text.replace("…", "...").encode("latin-1", errors="replace").decode("latin-1")
