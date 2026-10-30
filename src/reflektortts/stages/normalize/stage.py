"""The normalize stage plugin: prepares each line for its output language."""

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import StagePlugin, load_schema
from reflektortts.stages.normalize.english import EnglishWords
from reflektortts.stages.normalize.polish import PolishWords
from reflektortts.stages.normalize.text import Words, normalize

logger = logging.getLogger(__name__)

WORDS: dict[str, Words] = {"en": EnglishWords(), "pl": PolishWords()}


class Normalize:
    """Spells out numbers, money and percentages in the line's speech language; lines in a
    language without rules pass unchanged."""

    def __init__(self, languages: Mapping[str, Words]) -> None:
        self._languages = languages

    def process(self, event: TextEvent) -> TextEvent | None:
        words = self._languages.get(event.speech_language)
        if words is None:
            logger.debug("No normalization rules for %s", event.speech_language)
            return event
        return replace(event, text=normalize(event.text, words))


def create(settings: Mapping[str, Any]) -> Normalize:
    return Normalize(WORDS)


PLUGIN = StagePlugin(
    type="normalize",
    settings_schema=load_schema("reflektortts.stages.normalize", "normalize.schema.json"),
    create=create,
    summary="Spells out numbers and money",
)
