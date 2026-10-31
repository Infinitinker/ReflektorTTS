"""What the desktop app shows of the core's status."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreStatus:
    game: str | None
    """The title of the game being read, or None while waiting for one."""
    paused: bool


def parse_status(event: Mapping[str, Any]) -> CoreStatus | None:
    """The status in an /v1/events message, or None for other events."""
    if event.get("type") != "status":
        return None
    game = event.get("game")
    return CoreStatus(game=game["title"] if game else None, paused=bool(event.get("paused")))


def describe(status: CoreStatus | None) -> str:
    """One line for the window and the tray icon; status is None until the core answers."""
    if status is None:
        return "Starting…"
    text = f"Reading {status.game}" if status.game else "Waiting for a game"
    return f"{text} (paused)" if status.paused else text
