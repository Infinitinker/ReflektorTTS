"""Polish: kept names declined with the stand-in's ending, and "z"/"ze", "w"/"we" fitted to them."""

import re

from reflektortts.glossary import GlossaryTerm
from reflektortts.languages import NAME_ENDINGS

VOWELS = set("aeiouyąęó")

# The model declines a name ending in a vowel letter with an apostrophe ("Frenzy'ego", "Joe'go"),
# and the Moses detokenizer leaves a space before it. Only name endings are joined, so quotes stay
# apart.
_DETACHED_ENDING = re.compile(r"(?<=\w) '(?=(?:" + "|".join(NAME_ENDINGS["pl"]) + r")\b)")

# Prepositions with a longer form before some consonant clusters: "ze Sweetem", "we Wrocławiu".
_LONG_FORMS = {"z": "ze", "w": "we"}
_SHORT_FORMS = {long: short for short, long in _LONG_FORMS.items()}
_CLUSTER_STARTS = {"z": ("s", "z", "ś", "ź", "ż", "sz"), "w": ("w", "f")}


def _first_sound(word: str) -> tuple[str, str]:
    """The word's first sound and the rest, with "sz" one sound, as is "sh" in English names."""
    word = word.lower()
    if word[:2] in ("sz", "sh"):
        return "sz", word[2:]
    return word[:1], word[1:]


def _needs_long_form(short: str, word: str) -> bool:
    """Whether a preposition takes its long form before the word: before a cluster that starts
    with a sound like its own ("ze snu", "we wtorek"), not before a vowel ("z Sabiną")."""
    sound, rest = _first_sound(word)
    return sound in _CLUSTER_STARTS[short] and rest[:1].isalpha() and rest[:1] not in VOWELS


def _ends_in_k_or_g(word: str) -> bool:
    """Whether the word ends in a k or g sound, also with a silent final "e" ("Smoke")."""
    return word.lower().removesuffix("e").endswith(("k", "g"))


def _in_case_of(text: str, matched: str) -> str:
    if len(matched) > 1 and matched.isupper():
        return text.upper()
    return text[:1].upper() + text[1:] if matched[:1].isupper() else text


class Polish:
    def tidy(self, translated: str) -> str:
        return _DETACHED_ENDING.sub("'", translated)

    def declined(self, term: GlossaryTerm, ending: str) -> str:
        # A foreign woman's name ending in a consonant is not declined: "z Kendl".
        if term.female or not ending:
            return term.term
        # After k and g, "em" becomes "iem" ("Gregiem", "Smoke'iem", said "smołk"), and "ie"
        # becomes "u" ("o Gregu", where the stand-in has "o Kevinie").
        if _ends_in_k_or_g(term.pronounce.get("pl", term.term)):
            if ending == "ie":
                ending = "u"
            elif ending[0] == "e":
                ending = "i" + ending
        # An ending is set apart from a name ending in a vowel letter: "Smoke'a".
        return term.term + ("'" if term.term[-1].lower() in VOWELS else "") + ending

    def before(self, word: str, term: GlossaryTerm) -> str:
        short = _SHORT_FORMS.get(word.lower(), word.lower())
        if short not in _LONG_FORMS:
            return word
        # How the term sounds decides, so its Polish pronunciation counts when the glossary has one.
        spoken = term.pronounce.get("pl", term.term)
        fitted = _LONG_FORMS[short] if _needs_long_form(short, spoken) else short
        return _in_case_of(fitted, word)
