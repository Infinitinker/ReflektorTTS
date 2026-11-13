"""What the desktop app shows of the core's status."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreStatus:
    app: str | None
    """The title of the app being read, or None while waiting for one."""
    paused: bool
    profile: str | None = None
    """The ID of the profile the app is read with, or None while waiting for one."""
    unsupported: str | None = None
    """The title of an app running in a build its profile does not list, which is not read."""
    unsupported_sha256: str | None = None
    """That build's SHA-256, if it could be read."""
    voice: str = ""
    """The voice lines are spoken in, as "engine:name"."""
    input_language: str = "en"
    output_language: str = "en"
    ducking: bool = False
    """Whether the app's sound is lowered while a line is spoken."""
    duck_volume: float = 1.0
    """How far: the app's volume then, as a fraction of its own."""
    source_error: str | None = None
    """Why a source of the app being read fails, for the user, until it works again."""


def parse_status(event: Mapping[str, Any]) -> CoreStatus | None:
    """The status in an /v1/events message, or None for other events."""
    if event.get("type") != "status":
        return None
    app = event.get("app")
    unsupported = event.get("unsupported")
    source_error = event.get("source_error")
    return CoreStatus(
        app=app["title"] if app else None,
        paused=bool(event.get("paused")),
        profile=app.get("profile") if app else None,
        unsupported=unsupported["title"] if unsupported else None,
        unsupported_sha256=unsupported["sha256"] if unsupported else None,
        voice=str(event.get("voice", "")),
        input_language=str(event.get("input_language", "en")),
        output_language=str(event.get("output_language", "en")),
        ducking=bool(event.get("ducking")),
        duck_volume=float(event.get("duck_volume", 1.0)),
        source_error=source_error["message"] if source_error else None,
    )


def hint(status: CoreStatus | None) -> str:
    """A second line for the window: what to do now."""
    if status is not None and status.app and status.source_error:
        return status.source_error
    if status is not None and status.unsupported and not status.app:
        if status.unsupported_sha256 is None:
            return "Its executable could not be read to tell which version it is: see the log."
        return f"To support it, its profile needs this version’s SHA-256: {status.unsupported_sha256}"
    return "In an app with the overlay, open the panel with Ctrl+Shift+R."


def describe(status: CoreStatus | None) -> str:
    """One line for the window and the tray icon; status is None until the core answers."""
    if status is None:
        return "Starting…"
    if status.unsupported and not status.app:
        return f"This version of {status.unsupported} is not supported yet"
    text = f"Reading {status.app}" if status.app else "Waiting for an app"
    return f"{text} (paused)" if status.paused else text


def settings_caption(status: CoreStatus | None) -> str:
    """Whose settings the details are: the app's, or with none running, the ones a new app starts with."""
    if status is None:
        return ""
    if status.app:
        return f"Settings for {status.app}:"
    return "Settings a new app starts with:"


def status_languages(status: CoreStatus) -> tuple[str, ...]:
    """The app's language and the one lines are prepared in, or the one language if they are the same."""
    if status.input_language == status.output_language:
        return (status.input_language,)
    return (status.input_language, status.output_language)


def sound_text(status: CoreStatus) -> str:
    """What happens to the app's sound while a line is spoken."""
    if not status.ducking:
        return "Not lowered while a line is spoken"
    return f"Lowered to {round(status.duck_volume * 100)}% while a line is spoken"
