"""Replace stage: text replacements, e.g. removing an app's formatting marks."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.glossary import Glossaries
from reflektortts.pipeline.plugins import StagePlugin, load_schema


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    replacement: str
    literal: bool
    """A literal rule's replacement is inserted as is; a regex rule's may use \\1-style references."""

    def apply(self, text: str) -> str:
        if self.literal:
            return self.pattern.sub(lambda _: self.replacement, text)
        return self.pattern.sub(self.replacement, text)


def rule_from_settings(rule: Mapping[str, str]) -> Rule:
    if "pattern" in rule:
        return Rule(re.compile(rule["pattern"]), rule["replace"], literal=False)
    return Rule(re.compile(re.escape(rule["find"])), rule["replace"], literal=True)


class Replace:
    """Applies the rules in order, then trims surrounding spaces."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        self._rules = rules

    def process(self, event: TextEvent) -> TextEvent | None:
        text = event.text
        for rule in self._rules:
            text = rule.apply(text)
        return replace(event, text=text.strip())


def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Replace:
    return Replace([rule_from_settings(rule) for rule in settings["rules"]])


PLUGIN = StagePlugin(
    type="replace",
    settings_schema=load_schema("reflektortts.stages", "replace.schema.json"),
    create=create,
    summary="Removes formatting marks",
)
