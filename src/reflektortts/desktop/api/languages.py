"""The languages the core knows, from GET /v1/languages, and how the desktop app names them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ARROW = " → "
RULES_SEPARATOR = " · "
"""Between a language's speech rules, whose names may hold commas."""


@dataclass(frozen=True)
class LanguageItem:
    code: str
    name: str
    """In the language itself, e.g. "Polski"."""
    english_name: str
    speech_rules: tuple[str, ...]
    """What ReflektorTTS's stages do only for some output languages and do for this one, e.g.
    "Numbers, dates and units"."""


def parse_languages(data: Mapping[str, Any]) -> dict[str, LanguageItem]:
    """The answer to GET /v1/languages, by code."""
    return {
        language["code"]: LanguageItem(
            language["code"], language["name"], language["english_name"], tuple(language["speech_rules"])
        )
        for language in data["languages"]
    }


def speech_rules_text(code: str, languages: Mapping[str, LanguageItem]) -> str:
    """The speech rules of an output language, e.g. "Glossary grammar · Numbers, dates and units";
    empty for one without any, or that the core does not list."""
    language = languages.get(code)
    return "" if language is None else RULES_SEPARATOR.join(language.speech_rules)


def languages_text(codes: Sequence[str], languages: Mapping[str, LanguageItem]) -> str:
    """One language by its English name, then its own: "Polish (Polski)", or "English" where the two
    are the same. Two, a translation's from and to, by their English names: "English → Polish". A code
    the core does not list stands for itself."""
    if len(codes) == 1:
        language = languages.get(codes[0])
        if language is None:
            return codes[0]
        if language.name == language.english_name:
            return language.english_name
        return f"{language.english_name} ({language.name})"
    return ARROW.join(languages[code].english_name if code in languages else code for code in codes)
