"""Events the core produces: text on its way to sinks, plugin errors, and status changes."""

from dataclasses import dataclass

from reflektortts.languages import AUTO, DEFAULT_OUTPUT_LANGUAGE


@dataclass(frozen=True)
class TextEvent:
    """Text read from a source at a moment in time (monotonic seconds)."""

    source: str
    text: str
    time: float
    output_language: str = DEFAULT_OUTPUT_LANGUAGE
    """The language the line is prepared, spoken and shown in (ISO 639-1), from the player's settings."""
    game_language: str = AUTO
    """The language of the game's text (ISO 639-1), or "auto", from the player's settings."""


@dataclass(frozen=True)
class SubtitleEvent:
    """The subtitle to show over the game from now on; empty text hides it."""

    text: str


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
    """Identifies the stage within its profile, e.g. "subtitles/3:normalize"."""
    type: str
    summary: str
    warning: str | None
    """Shown while the stage is switched off, if switching it off breaks reading."""
    enabled: bool


@dataclass(frozen=True)
class SourceStages:
    """One source of the game being read and its stages, as the player sees them."""

    source: str
    type: str
    """The source plugin, e.g. "memory"."""
    enabled: bool
    stages: tuple[StageState, ...]


@dataclass(frozen=True)
class Status:
    """What the core is doing; published whenever any of it changes."""

    game: GameInfo | None
    """The game being read, or None while waiting for one."""
    voice: str
    game_language: str
    output_language: str
    paused: bool
    ducking: bool
    """Whether the game's sound is lowered while lines are spoken."""
    duck_volume: float
    """The game's volume while lines are spoken, as a fraction of its own volume."""
    speech_rate: float
    """How fast lines are spoken, as a multiple of the voice's own pace."""
    cut_off_lines: bool
    """Whether a new line cuts off the one being spoken; otherwise lines wait their turn."""
    subtitles: bool
    """Whether lines are shown as subtitles over the game."""
    subtitle_size: str
    subtitle_position: str
    sources: tuple[SourceStages, ...] = ()
    """The stages of the game being read, per source; empty while waiting for a game."""
