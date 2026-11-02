"""Events the core produces: text on its way to sinks, plugin errors, and status changes."""

from dataclasses import dataclass
from enum import StrEnum

from reflektortts.languages import DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE


class Output(StrEnum):
    """What a line is prepared for. Each source's stages run once for each, so a stage can be on
    for one and off for the other."""

    TEXT = "text"
    """The text shown: subtitles, and the lines the API reports."""
    SPEECH = "speech"
    """What is spoken."""


@dataclass(frozen=True)
class TextEvent:
    """Text read from a source at a moment in time (monotonic seconds)."""

    source: str
    text: str
    time: float
    output_language: str = DEFAULT_OUTPUT_LANGUAGE
    """The language the line is prepared, spoken and shown in (ISO 639-1), from the user's settings."""
    input_language: str = DEFAULT_INPUT_LANGUAGE
    """The language of the app's text (ISO 639-1), from the user's settings."""


@dataclass(frozen=True)
class SubtitleEvent:
    """The subtitle to show over the app from now on; empty text hides it."""

    text: str


@dataclass(frozen=True)
class ErrorEvent:
    """A plugin failed. kind is e.g. "source.error" or "sink.error"; message is for the user."""

    kind: str
    origin: str
    message: str


@dataclass(frozen=True)
class DownloadEvent:
    """A download the user started moved on: state is "downloading" (with done and total bytes,
    total if known), "installed", "failed" (with a message for the user) or "removed"."""

    entry_id: str
    state: str
    done: int = 0
    total: int | None = None
    message: str = ""


@dataclass(frozen=True)
class PreviewEvent:
    """A voice preview started (playing, also while its voice loads) or ended (not playing): it was
    spoken, cut off by another preview, or its voice could not be loaded."""

    voice: str
    playing: bool


@dataclass(frozen=True)
class AppInfo:
    title: str
    pid: int


@dataclass(frozen=True)
class UnsupportedApp:
    """A program with a profile is running, but in a build the profile does not list."""

    title: str
    sha256: str | None
    """Its executable's SHA-256, for whoever adds the build to the profile; None if unreadable."""


@dataclass(frozen=True)
class StageState:
    """One stage of the app being read, as the user sees it."""

    key: str
    """Identifies the stage within its profile, e.g. "subtitles/3:normalize"."""
    type: str
    summary: str
    warning: str | None
    """Shown while the stage is switched off, if switching it off breaks reading."""
    enabled: dict[Output, bool]
    """Whether the stage is on, for the text shown and for speech: as the user switched it, else
    as its profile starts it."""
    inactive: str | None = None
    """Why the stage does nothing with the user's languages, or None if it works with them."""


@dataclass(frozen=True)
class SourceStages:
    """One source of the app being read and its stages, as the user sees them."""

    source: str
    type: str
    """The source plugin, e.g. "memory"."""
    enabled: bool
    stages: tuple[StageState, ...]


@dataclass(frozen=True)
class Status:
    """What the core is doing; published whenever any of it changes."""

    app: AppInfo | None
    """The app being read, or None while waiting for one."""
    voice: str
    input_language: str
    output_language: str
    paused: bool
    ducking: bool
    """Whether the app's sound is lowered while lines are spoken."""
    duck_volume: float
    """The app's volume while lines are spoken, as a fraction of its own volume."""
    speech_rate: float
    """How fast lines are spoken, as a multiple of the voice's own pace."""
    new_line: str
    """What a new line does while another is spoken: "wait", "cut_off" or "speed_up"."""
    subtitles: bool
    """Whether lines are shown as subtitles over the app."""
    subtitle_size: str
    subtitle_position: str
    sources: tuple[SourceStages, ...] = ()
    """The stages of the app being read, per source; empty while waiting for an app."""
    unsupported: UnsupportedApp | None = None
    """A running app in a build its profile does not list, which is not read."""
