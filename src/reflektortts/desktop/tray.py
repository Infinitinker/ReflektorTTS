"""The desktop app's icon next to the clock, with its menu. pystray runs it on a thread of its own,
so the menu's actions are called on that thread."""

import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw, ImageFont

ICON_SIZE = 64
ICON_COLOR = (214, 120, 32)


def icon_image() -> Image.Image:
    """A round badge with an R."""
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, ICON_SIZE - 2, ICON_SIZE - 2), fill=ICON_COLOR)
    font = ImageFont.load_default(size=40)
    draw.text((ICON_SIZE / 2, ICON_SIZE / 2), "R", font=font, fill="white", anchor="mm")
    return image


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
        self._icon = pystray.Icon("ReflektorTTS", icon_image(), "ReflektorTTS", menu)
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

    def notify(self, message: str) -> None:
        self._icon.notify(message, "ReflektorTTS")
