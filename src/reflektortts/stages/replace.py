"""Replace stage: plain text replacements, e.g. removing a game's formatting marks."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import StagePlugin, load_schema


class Replace:
    """Applies (find, replacement) pairs in order, then trims surrounding spaces."""

    def __init__(self, rules: Sequence[tuple[str, str]]) -> None:
        self._rules = rules

    def process(self, event: TextEvent) -> TextEvent | None:
        text = event.text
        for find, replacement in self._rules:
            text = text.replace(find, replacement)
        return replace(event, text=text.strip())


def create(settings: Mapping[str, Any]) -> Replace:
    return Replace([(rule["find"], rule["replace"]) for rule in settings["rules"]])


PLUGIN = StagePlugin(
    type="replace", settings_schema=load_schema("reflektortts.stages", "replace.schema.json"), create=create
)
