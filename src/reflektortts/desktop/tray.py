"""The desktop app's icon next to the clock, with its menu. pystray runs it on a thread of its own,
so the menu's actions are called on that thread."""

import threading
from collections.abc import Callable

import pystray

from reflektortts.desktop.icon import icon_image

TRAY_ICON_SIZE = 32
"""The largest size a tray shows; the icon's simple drawing, which stays clear when scaled down."""


class Tray:
    def __init__(
        self, on_open: Callable[[], None], on_pause_toggle: Callable[[], None], on_quit: Callable[[], None]
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
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: on_quit()),
        )
        self._icon = pystray.Icon("ReflektorTTS", icon_image(TRAY_ICON_SIZE), "ReflektorTTS", menu)
        self._thread = threading.Thread(target=self._icon.run, name="tray", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._icon.stop()
        self._thread.join()

    def show_status(self, text: str, paused: bool, connected: bool) -> None:
        self._paused = paused
        self._connected = connected
        self._icon.title = f"ReflektorTTS: {text}"
        self._icon.update_menu()

    def notify(self, title: str, message: str) -> None:
        """Windows puts the app's name above the title, so the title says something of its own."""
        self._icon.notify(message, title)
