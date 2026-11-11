"""Tracker stage: passes a line on once it has settled, and only once."""

from collections.abc import Mapping
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.glossary import Glossaries
from reflektortts.letters import letter_count
from reflektortts.pipeline.plugins import StagePlugin, load_schema

# Lines that are mostly symbols or digits are garbage or HUD readouts, not dialogue.
MIN_LETTER_SHARE = 0.5


class Tracker:
    """Passes a line on once it has stayed unchanged for stable_seconds.

    Sources report the same text on every poll, and some games type text out letter by
    letter; the tracker turns that into one event per line. A line is passed on again
    only after the text has disappeared or changed in between.
    """

    def __init__(self, stable_seconds: float, min_letters: int) -> None:
        self._stable_seconds = stable_seconds
        self._min_letters = min_letters
        self._candidate = ""
        self._since = 0.0
        self._passed = ""

    def process(self, event: TextEvent) -> TextEvent | None:
        if event.text != self._candidate:
            self._candidate = event.text
            self._since = event.time
        if not event.text:
            self._passed = ""
            return None
        if event.text == self._passed or event.time - self._since < self._stable_seconds:
            return None
        if not self._looks_like_a_line(event.text):
            return None
        self._passed = event.text
        return event

    def _looks_like_a_line(self, text: str) -> bool:
        letters = letter_count(text)
        visible = sum(not character.isspace() for character in text)
        return letters >= self._min_letters and letters >= MIN_LETTER_SHARE * visible


def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Tracker:
    return Tracker(stable_seconds=settings.get("stable_ms", 500) / 1000, min_letters=settings.get("min_letters", 4))


PLUGIN = StagePlugin(
    type="tracker",
    settings_schema=load_schema("reflektortts.stages", "tracker.schema.json"),
    create=create,
    summary="Waits until a line settles",
    warning_when_disabled="Needed: or the voice restarts on every reading",
)
