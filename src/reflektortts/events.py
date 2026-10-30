"""Events that flow from sources through stages to sinks, and errors reported about them."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextEvent:
    """Text read from a source at a moment in time (monotonic seconds)."""

    source: str
    text: str
    time: float


@dataclass(frozen=True)
class ErrorEvent:
    """A plugin failed. kind is e.g. "source.error" or "sink.error"; message is for the user."""

    kind: str
    origin: str
    message: str
