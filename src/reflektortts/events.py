"""Events the core produces: text on its way to sinks, plugin errors, and status changes."""

from dataclasses import dataclass

from reflektortts.languages import DEFAULT_LANGUAGE


@dataclass(frozen=True)
class TextEvent:
    """Text read from a source at a moment in time (monotonic seconds)."""

    source: str
    text: str
    time: float
    language: str = DEFAULT_LANGUAGE
    """The output language the line should end up in (ISO 639-1), from the user's settings."""


@dataclass(frozen=True)
class ErrorEvent:
    """A plugin failed. kind is e.g. "source.error" or "sink.error"; message is for the user."""

    kind: str
    origin: str
    message: str


@dataclass(frozen=True)
class GameInfo:
    title: str
    pid: int


@dataclass(frozen=True)
class Status:
    """What the core is doing; published whenever any of it changes."""

    game: GameInfo | None
    """The game being read, or None while waiting for one."""
    voice: str
    language: str
    """Output language (ISO 639-1)."""
    paused: bool
