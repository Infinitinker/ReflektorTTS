"""Contracts for source, stage and sink plugins."""

from enum import StrEnum
from typing import Protocol

from reflektortts.events import TextEvent
from reflektortts.languages import Languages


class Output(StrEnum):
    """What a line is prepared for. Each source's stages run once for each, so a stage can be on
    for one and off for the other."""

    TEXT = "text"
    """The text shown: subtitles, and the lines the API reports."""
    SPEECH = "speech"
    """What is spoken."""


class Source(Protocol):
    """Reads the app's current text when polled."""

    name: str
    poll_interval: float
    """Seconds between reads."""

    def read(self, languages: Languages) -> str | None:
        """Returns the text shown right now, or None if there is none. Raises if reading fails.

        languages are the user's; a source that can read the text in several languages reads it
        in the input language.
        """

    def close(self) -> None: ...


class Stage(Protocol):
    """Transforms or filters text on its way to the sinks."""

    def process(self, event: TextEvent) -> TextEvent | None:
        """Returns the event to pass on, possibly changed, or None to drop it.

        Empty text means the source currently has none.
        """


class Sink(Protocol):
    """Does something with finished text, e.g. speaks it."""

    name: str

    def deliver(self, event: TextEvent) -> None: ...

    def close(self) -> None: ...
