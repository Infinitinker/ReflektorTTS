"""What the desktop app remembers about itself between runs, apart from the settings for reading
apps: desktop.json in the user's state folder."""

from dataclasses import asdict, dataclass
from pathlib import Path

from reflektortts.settings import read_json_object, write_json_object

STATE_FILE = "desktop.json"


@dataclass(frozen=True)
class DesktopState:
    told_about_tray: bool = False
    """Whether the user was told, when they first closed the window, that ReflektorTTS keeps running."""


def load_state(directory: Path) -> DesktopState:
    """The saved state; a missing or broken file gives the defaults."""
    data = read_json_object(directory / STATE_FILE)
    return DesktopState(told_about_tray=data.get("told_about_tray") is True)


def save_state(state: DesktopState, directory: Path) -> None:
    write_json_object(directory / STATE_FILE, asdict(state))
