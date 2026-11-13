"""Languages: what the text read is in, and what lines are spoken and shown in.

ReflektorTTS knows every ISO 639-1 language, from languages.json, which tools/languages.py
generates; how well each one is read depends on the translation models and voices there are for it,
and on the rules plugins have for it.
"""

import json
from dataclasses import dataclass
from importlib.resources import files

DEFAULT_INPUT_LANGUAGE = "en"
DEFAULT_OUTPUT_LANGUAGE = "en"


@dataclass(frozen=True)
class Language:
    code: str
    """ISO 639-1, as everywhere in ReflektorTTS."""
    name: str
    """The language's own name, as shown to users ("Deutsch")."""
    english_name: str
    iso639_2b: str
    """The ISO 639-2 bibliographic code ("ger"), which some apps name their files with."""
    iso639_2t: str
    """The ISO 639-2 terminologic code ("deu"), the same as iso639_2b for most languages."""
    code_page: str | None
    """The Windows code page text in the language usually comes in when it is not UTF-8, as a
    Python codec ("cp1250"); None for languages whose text is Unicode only."""
    separates_words: bool
    """False for languages written without spaces between words, such as Chinese and Thai."""


ALIASES = {"fil": "tl", "no": "nb", "pb": "pt", "zt": "zh"}
"""Codes catalogs and systems use for languages that have another code here: Filipino voices are
Tagalog, Norwegian ones speak Bokmål, and Argos Translate's Brazilian Portuguese and Traditional
Chinese models are copies of its Portuguese and Chinese ones."""


def _load() -> dict[str, Language]:
    rows = json.loads(files("reflektortts").joinpath("languages.json").read_text("utf-8"))
    return {code: Language(code=code, **row) for code, row in rows.items()}


_TABLE = _load()
LANGUAGES = {code: language for code, language in _TABLE.items() if code not in ALIASES}
"""Every ISO 639-1 language but those known here by another code, as Norwegian is by Bokmål's."""

# A sentence in each language, spoken to let the user hear a voice; a voice in another language
# speaks the language's name.
SAMPLES = {
    "de": "So liest diese Stimme deine Apps vor.",
    "en": "This is how this voice reads your apps.",
    "es": "Así lee esta voz tus aplicaciones.",
    "fr": "Voici comment cette voix lit vos applications.",
    "it": "Ecco come questa voce legge le tue app.",
    "pl": "Tak ten głos czyta twoje gry.",
}


# Endings a language adds to a foreign name as it declines it, e.g. Polish "Carla", "Carlowi",
# "Smoke'a"; a language without them does not decline names.
NAME_ENDINGS = {
    "pl": ("ego", "go", "emu", "mu", "iem", "em", "m", "a", "u", "ie", "owi", "y", "ów", "om", "ami", "ach"),
}


class LanguageError(Exception):
    """A language is not known."""


@dataclass(frozen=True)
class Languages:
    input: str
    """The language of the text read (ISO 639-1)."""
    output: str
    """The language lines are prepared, spoken and shown in (ISO 639-1)."""


def primary_language(tag: str) -> str:
    """The language of a tag, as a code here: "pl-PL" is "pl", "no_NO" is "nb"."""
    code = tag.split("-")[0].split("_")[0].lower()
    return ALIASES.get(code, code)


def language_tag(tag: str) -> str:
    """A BCP 47 tag with its language as a code here: "no_NO" is "nb-NO", "fil-PH" is "tl-PH"."""
    language, _, rest = tag.replace("_", "-").partition("-")
    code = primary_language(language)
    return f"{code}-{rest}" if rest else code


def check_language(code: str) -> None:
    if code in ALIASES and ALIASES[code] in LANGUAGES:
        known = LANGUAGES[ALIASES[code]]
        raise LanguageError(
            f'Use "{known.code}" ({known.english_name}) instead of "{code}": ReflektorTTS knows it by that code.'
        )
    if code not in LANGUAGES:
        raise LanguageError(f'There is no language "{code}": use its two-letter ISO 639-1 code, such as "en".')


def separates_words(code: str) -> bool:
    """Whether the language puts spaces between words, as most do; Chinese and Thai do not."""
    return code not in LANGUAGES or LANGUAGES[code].separates_words


def alias_names(code: str) -> tuple[str, ...]:
    """The English and own names of the languages known here by the language's code: "Norwegian"
    and "Norsk" for "nb"."""
    aliases = [_TABLE[alias] for alias, target in ALIASES.items() if target == code and alias in _TABLE]
    return tuple(name for alias in aliases for name in (alias.english_name, alias.name))


def other_codes(code: str) -> frozenset[str]:
    """The other codes the language is written with, by apps and catalogs: "no" and "nor" for "nb"."""
    aliases = {alias for alias, target in ALIASES.items() if target == code}
    iso_codes = {
        other for alias in aliases if alias in _TABLE for other in (_TABLE[alias].iso639_2b, _TABLE[alias].iso639_2t)
    }
    return frozenset(aliases | iso_codes)


def language_name(code: str) -> str:
    """The language's English name, as messages give it; the code in quotes if it is not known."""
    return LANGUAGES[code].english_name if code in LANGUAGES else f'"{code}"'


def sample(code: str) -> str:
    """The sentence a voice in the language speaks to be heard, or the language's own name."""
    check_language(code)
    return SAMPLES.get(code, LANGUAGES[code].name)
