"""Languages: what the game's text is in, and what lines are spoken and shown in."""

from dataclasses import dataclass

DEFAULT_OUTPUT_LANGUAGE = "en"
AUTO = "auto"
"""Game language meaning "detect it", e.g. left to the translation engine."""

# ISO 639-1 code mapped to the language's own name, as shown to users.
LANGUAGES = {
    "en": "English",
    "pl": "Polski",
}


class LanguageError(Exception):
    """A language is not supported; the message lists the supported ones."""


@dataclass(frozen=True)
class Languages:
    game: str
    """The language of the game's text (ISO 639-1), or AUTO."""
    output: str
    """The language lines are prepared, spoken and shown in (ISO 639-1)."""


def primary_language(tag: str) -> str:
    """The language part of a tag: "pl-PL" is "pl"."""
    return tag.split("-")[0].split("_")[0].lower()


def check_output_language(code: str) -> None:
    if code not in LANGUAGES:
        raise LanguageError(f'There is no language "{code}". Available: {", ".join(LANGUAGES)}.')


def check_game_language(code: str) -> None:
    if code != AUTO and code not in LANGUAGES:
        raise LanguageError(f'There is no language "{code}". Available: {AUTO}, {", ".join(LANGUAGES)}.')
