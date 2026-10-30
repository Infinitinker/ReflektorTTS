"""Events the core produces: text on its way to sinks, plugin errors, and status changes."""

from dataclasses import dataclass

from reflektortts.languages import AUTO, DEFAULT_SPEECH_LANGUAGE


@dataclass(frozen=True)
class TextEvent:
    """Text read from a source at a moment in time (monotonic seconds)."""

    source: str
    text: str
    time: float
    speech_language: str = DEFAULT_SPEECH_LANGUAGE
    """The language the line should be spoken in (ISO 639-1), from the player's settings."""
    game_language: str = AUTO
    """The language of the game's text (ISO 639-1), or "auto", from the player's settings."""


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
class StageState:
    """One stage of the game being read, as the player sees it."""

    key: str
    """Identifies the stage within its profile, e.g. "messages/2:normalize"."""
    type: str
    summary: str
    warning: str | None
    """Shown while the stage is switched off, if switching it off breaks reading."""
    enabled: bool


@dataclass(frozen=True)
class SourceStages:
    source: str
    stages: tuple[StageState, ...]


@dataclass(frozen=True)
class Status:
    """What the core is doing; published whenever any of it changes."""

    game: GameInfo | None
    """The game being read, or None while waiting for one."""
    voice: str
    game_language: str
    speech_language: str
    paused: bool
    sources: tuple[SourceStages, ...] = ()
    """The stages of the game being read, per source; empty while waiting for a game."""
