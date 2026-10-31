"""The normalize stage plugin: prepares each line for its output language."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import StagePlugin, load_schema
from reflektortts.stages.normalize.english import EnglishWords
from reflektortts.stages.normalize.polish import PolishWords
from reflektortts.stages.normalize.text import Words, normalize

WORDS: dict[str, Words] = {"en": EnglishWords(), "pl": PolishWords()}


class Normalize:
    """Spells out numbers, money and percentages in the line's output language. It runs only for
    languages inactive_reason accepts."""

    def __init__(self, languages: Mapping[str, Words]) -> None:
        self._languages = languages

    def process(self, event: TextEvent) -> TextEvent | None:
        return replace(event, text=normalize(event.text, self._languages[event.output_language]))


def inactive_reason(languages: Languages) -> str | None:
    return None if languages.output in WORDS else "No rules for the output language yet"


def create(settings: Mapping[str, Any]) -> Normalize:
    return Normalize(WORDS)


PLUGIN = StagePlugin(
    type="normalize",
    settings_schema=load_schema("reflektortts.stages.normalize", "normalize.schema.json"),
    create=create,
    summary="Spells out numbers and money",
    inactive_reason=inactive_reason,
)
