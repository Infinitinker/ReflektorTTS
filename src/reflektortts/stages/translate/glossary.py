"""Applies a profile's glossary around translation.

Kept terms are swapped for stand-in names before translating, because the model leaves names
untranslated but declines them, and swapped back after as the output language's rules say, e.g.
in Polish with the stand-in's ending ("Kevinowi" becomes "Sweetowi"). Terms with a meaning are
rewritten in its plain words.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from reflektortts.glossary import Glossary, GlossaryTerm, TermFinder, word_bounded
from reflektortts.letters import LATIN_LETTER, letter_count
from reflektortts.stages.translate.languages import OutputLanguage

# English names, for English input: the English-Polish model keeps them and declines them with an
# unchanged stem. One is used per kept term in a line, so a line can hold that many. Women's names
# lose their final "a" ("Linda", "Lindzie", "Lindą"), so their stem is the name without it. No stem
# begins another common word, e.g. not "Paul" of "Paula".
MALE_STAND_INS = ("Kevin", "Brian", "Steven", "Dennis", "Jason", "Robert", "Edward", "Howard", "Gordon", "Norman")
FEMALE_STAND_INS = ("Linda", "Laura", "Sandra", "Diana", "Nina", "Teresa", "Tina", "Brenda", "Gloria", "Olivia")


def _stem(stand_in: str, female: bool) -> str:
    """What every declined form of the stand-in begins with."""
    return stand_in[:-1] if female else stand_in


def _whole_words(terms: Sequence[str], separates_words: bool, flags: re.RegexFlag) -> re.Pattern[str] | None:
    """Matches any of the terms as whole words, the longest first; None if there are none."""
    if not terms:
        return None
    longest_first = sorted(set(terms), key=len, reverse=True)
    return re.compile(word_bounded("|".join(map(re.escape, longest_first)), separates_words), flags)


def _in_case_of(text: str, matched: str) -> str:
    """The text in capitals if matched is, or capitalized if matched is."""
    if len(matched) > 1 and matched.isupper():
        return text.upper()
    if matched[:1].isupper():
        return text[:1].upper() + text[1:]
    return text


@dataclass(frozen=True)
class _StandIn:
    term: GlossaryTerm
    pattern: re.Pattern[str]
    """The stand-in in any case, with the ending the model gave it, and the word before it."""

    def put_back(self, match: re.Match[str], language: OutputLanguage) -> str:
        shouted = match.group("stand_in").isupper()
        text = language.declined(self.term, match.group("ending"))
        before = match.group("before")
        if before is not None:
            fitted = language.before(before, self.term)
            text = (fitted.upper() if shouted else fitted) + match.group("gap") + text
        return text.upper() if shouted else text


@dataclass(frozen=True)
class Prepared:
    """A line ready for the model, and the stand-ins to put back in its translation."""

    text: str
    stand_ins: tuple[_StandIn, ...] = ()

    def put_back(self, translated: str, language: OutputLanguage) -> str:
        for stand_in in self.stand_ins:
            translated = stand_in.pattern.sub(partial(stand_in.put_back, language=language), translated)
        return translated


class GlossaryRules:
    """What translation does with a profile's glossary terms, in lines of the glossary's language,
    which may be written without spaces between words."""

    def __init__(self, glossary: Glossary, separates_words: bool = True) -> None:
        self._kept = TermFinder(term for term in glossary if term.keep)
        self._keep = self._kept.whole_words(separates_words)
        self._meanings: dict[str, str] = {}
        for term in glossary:
            if term.means is not None:
                self._meanings.update(dict.fromkeys((spelling.lower() for spelling in term.spellings), term.means))
        self._means = _whole_words(list(self._meanings), separates_words, re.IGNORECASE)
        # The skip count sets aside kept terms and those only pronounced differently, such as names.
        self._set_aside = TermFinder(term for term in glossary if term.keep or term.pronounce).whole_words(
            separates_words
        )
        self.key = tuple((term.spellings, term.keep, term.female, term.means) for term in glossary)
        """Tells glossaries apart in a cache of translations."""

    def letters_besides_terms(self, text: str) -> int:
        """Letters of the line outside its kept and pronounced terms."""
        if self._set_aside is not None:
            text = self._set_aside.sub("", text)
        return letter_count(text)

    def prepare(self, text: str) -> Prepared:
        if self._means is not None:
            text = self._means.sub(
                lambda match: _in_case_of(self._meanings[match.group(0).lower()], match.group(0)), text
            )
        if self._keep is None:
            return Prepared(text)
        # A stand-in is found again by its stem, so one whose stem the line has ("Lind" of "Lindsay")
        # is not used.
        in_line = text.lower()
        free = {
            female: [name for name in candidates if _stem(name, female).lower() not in in_line]
            for female, candidates in ((False, MALE_STAND_INS), (True, FEMALE_STAND_INS))
        }
        names: dict[frozenset[str], str] = {}
        """Kept terms of this line, by their spellings, and their stand-ins."""
        stand_ins: list[_StandIn] = []

        def stand_in(match: re.Match[str]) -> str:
            # The term is put back as this line first spells it.
            term, shouted = self._kept.found(match.group(0))
            spellings = frozenset(term.spellings)
            if spellings not in names:
                if not free[term.female]:
                    return match.group(0)  # More kept terms in one line than stand-ins: left as is.
                name = free[term.female].pop(0)
                names[spellings] = name
                stem = _stem(name, term.female)
                pattern = (
                    rf"(?:(?<!\w)(?P<before>\w+)(?P<gap>\s+))?"
                    rf"(?<!{LATIN_LETTER})(?P<stand_in>{stem}(?P<ending>{LATIN_LETTER}*))"
                )
                stand_ins.append(_StandIn(term, re.compile(pattern, re.IGNORECASE)))
            return names[spellings].upper() if shouted else names[spellings]

        return Prepared(self._keep.sub(stand_in, text), tuple(stand_ins))
