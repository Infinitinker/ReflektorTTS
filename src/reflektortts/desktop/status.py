"""What the desktop app shows of the core's status."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreStatus:
    game: str | None
    """The title of the game being read, or None while waiting for one."""
    paused: bool
    unsupported: str | None = None
    """The title of a game running in a build its profile does not list, which is not read."""
    unsupported_sha256: str | None = None
    """That build's SHA-256, if it could be read."""


def parse_status(event: Mapping[str, Any]) -> CoreStatus | None:
    """The status in an /v1/events message, or None for other events."""
    if event.get("type") != "status":
        return None
    game = event.get("game")
    unsupported = event.get("unsupported")
    return CoreStatus(
        game=game["title"] if game else None,
        paused=bool(event.get("paused")),
        unsupported=unsupported["title"] if unsupported else None,
        unsupported_sha256=unsupported["sha256"] if unsupported else None,
    )


def hint(status: CoreStatus | None) -> str:
    """A second line for the window: what to do now."""
    if status is not None and status.unsupported and not status.game:
        if status.unsupported_sha256 is None:
            return "Its executable could not be read to tell which version it is; see the log."
        return f"To support it, its profile needs this version's SHA-256: {status.unsupported_sha256}"
    return "In an app with the overlay, open the ReflektorTTS panel with Ctrl+Shift+R."


def describe(status: CoreStatus | None) -> str:
    """One line for the window and the tray icon; status is None until the core answers."""
    if status is None:
        return "Starting…"
    if status.unsupported and not status.game:
        return f"This version of {status.unsupported} is not supported yet"
    text = f"Reading {status.game}" if status.game else "Waiting for an app"
    return f"{text} (paused)" if status.paused else text
