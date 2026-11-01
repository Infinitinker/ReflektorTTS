"""Languages: what the text read is in, and what lines are spoken and shown in."""

from dataclasses import dataclass

DEFAULT_INPUT_LANGUAGE = "en"
DEFAULT_OUTPUT_LANGUAGE = "en"

# ISO 639-1 code mapped to the language's own name, as shown to users.
LANGUAGES = {
    "en": "English",
    "pl": "Polski",
}

# A sentence in each language, spoken to let the player hear a voice.
SAMPLES = {
    "en": "This is how this voice reads your games.",
    "pl": "Tak ten głos czyta twoje gry.",
}


class LanguageError(Exception):
    """A language is not supported; the message lists the supported ones."""


@dataclass(frozen=True)
class Languages:
    input: str
    """The language of the text read (ISO 639-1)."""
    output: str
    """The language lines are prepared, spoken and shown in (ISO 639-1)."""


def primary_language(tag: str) -> str:
    """The language part of a tag: "pl-PL" is "pl"."""
    return tag.split("-")[0].split("_")[0].lower()


def check_language(code: str) -> None:
    if code not in LANGUAGES:
        raise LanguageError(f'There is no language "{code}". Available: {", ".join(LANGUAGES)}.')
