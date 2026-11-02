"""Pronounce stage: respells glossary terms so a voice pronounces them right, e.g. "Carl" as
"Karl" in Polish, keeping the ending the term was declined with ("Carlowi" becomes "Karlowi")."""

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.glossary import Glossaries, TermFinder
from reflektortts.languages import NAME_ENDINGS
from reflektortts.pipeline.plugins import StagePlugin, load_schema


class _Respelling:
    """A language's respelled terms, and how to find them."""

    def __init__(self, terms: TermFinder, language: str) -> None:
        self._terms = terms
        self._language = language
        endings = NAME_ENDINGS.get(language, ())
        # An ending may follow an apostrophe ("Smoke'a"); it is spoken without it.
        declined = (
            r"(?:'?(?P<ending>(?i:" + "|".join(sorted(endings, key=len, reverse=True)) + ")))?" if endings else ""
        )
        self._pattern = re.compile(rf"(?<!\w)(?P<term>{terms.alternation}){declined}(?!\w)")

    def apply(self, text: str) -> str:
        return self._pattern.sub(self._respell, text)

    def _respell(self, match: re.Match[str]) -> str:
        term, shouted = self._terms.found(match.group("term"))
        spoken = term.pronounce[self._language]
        return (spoken.upper() if shouted else spoken) + (match.groupdict().get("ending") or "")


class Pronounce:
    """Respells the terms of the glossary for the line's input language that have a pronunciation
    for its output language."""

    def __init__(self, glossaries: Glossaries) -> None:
        self._glossaries = glossaries
        self._respellings: dict[tuple[str, str], _Respelling | None] = {}

    def process(self, event: TextEvent) -> TextEvent | None:
        respelling = self._respelling(event.input_language, event.output_language)
        if respelling is None or not event.text:
            return event
        return replace(event, text=respelling.apply(event.text))

    def _respelling(self, read_in: str, spoken_in: str) -> _Respelling | None:
        languages = (read_in, spoken_in)
        if languages not in self._respellings:
            glossary = self._glossaries.get(read_in, ())
            terms = TermFinder(term for term in glossary if spoken_in in term.pronounce)
            self._respellings[languages] = _Respelling(terms, spoken_in) if terms else None
        return self._respellings[languages]


def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Pronounce:
    return Pronounce(glossaries)


PLUGIN = StagePlugin(
    type="pronounce",
    settings_schema=load_schema("reflektortts.stages", "pronounce.schema.json"),
    create=create,
    summary="Respells terms so they sound right",
)
