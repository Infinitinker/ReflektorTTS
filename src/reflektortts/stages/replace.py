"""Replace stage: text replacements, e.g. removing an app's formatting marks."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import regex

from reflektortts.events import TextEvent
from reflektortts.glossary import Glossaries
from reflektortts.pipeline.plugins import StagePlugin, load_schema

TIMEOUT = 0.1
"""Seconds a rule may take on one line. Python's own re has no limit, so a pattern from a shared
profile that backtracks without end would freeze ReflektorTTS; the regex package stops it."""


class RuleTimeoutError(Exception):
    """A rule took longer than TIMEOUT on a line."""


@dataclass(frozen=True)
class Rule:
    pattern: regex.Pattern[str]
    replacement: str
    literal: bool
    """A literal rule's replacement is inserted as is; a regex rule's may use \\1-style references."""

    def apply(self, text: str) -> str:
        """Raises RuleTimeoutError if the rule takes longer than TIMEOUT."""
        try:
            if self.literal:
                return self.pattern.sub(lambda _: self.replacement, text, timeout=TIMEOUT)
            return self.pattern.sub(self.replacement, text, timeout=TIMEOUT)
        except TimeoutError as error:
            raise RuleTimeoutError(
                f'The pattern "{self.pattern.pattern}" took too long on a line, so the line was skipped. '
                "Make the pattern simpler in the profile, e.g. without a repeat inside a repeat"
            ) from error


def rule_from_settings(rule: Mapping[str, str]) -> Rule:
    """Raises ValueError, in user terms, for a replacement its pattern cannot fill in.

    The profile's schema has checked the pattern with Python's re, whose syntax regex also accepts.
    The replacement is checked with re too: regex reads it only once the pattern matches."""
    if "pattern" in rule:
        try:
            re.compile(rule["pattern"]).sub(rule["replace"], "")
        except (re.error, IndexError) as error:
            raise ValueError(
                f'the replacement "{rule["replace"]}" does not fit the pattern "{rule["pattern"]}": {error}. '
                "Use \\1, \\2… only for groups the pattern has, and write each backslash twice in JSON"
            ) from error
        return Rule(regex.compile(rule["pattern"]), rule["replace"], literal=False)
    return Rule(regex.compile(regex.escape(rule["find"])), rule["replace"], literal=True)


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
