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

from reflektortts.glossary import Glossary, GlossaryTerm
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


def _whole_words(terms: Sequence[str], flags: re.RegexFlag = re.NOFLAG) -> re.Pattern[str] | None:
    """Matches any of the terms as whole words, the longest first; None if there are none."""
    if not terms:
        return None
    longest_first = sorted(set(terms), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, longest_first)) + r")(?!\w)", flags)


def _as_written(term: GlossaryTerm) -> tuple[str, str]:
    """A term as an app writes it: as in the glossary, and in capitals in shouted lines."""
    return term.term, term.term.upper()


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
    """What translation does with a profile's glossary terms."""

    def __init__(self, glossary: Glossary) -> None:
        self._kept = {written: term for term in glossary if term.keep for written in _as_written(term)}
        self._keep = _whole_words(list(self._kept))
        self._meanings: dict[str, str] = {}
        for term in glossary:
            if term.means is not None:
                self._meanings[term.term.lower()] = term.means
        self._means = _whole_words(list(self._meanings), re.IGNORECASE)
        # The skip count sets aside kept terms and those only pronounced differently, such as names.
        self._set_aside = _whole_words(
            [written for term in glossary if term.keep or term.pronounce for written in _as_written(term)]
        )
        self.key = tuple((term.term, term.keep, term.female, term.means) for term in glossary)
        """Tells glossaries apart in a cache of translations."""

    def letters_besides_terms(self, text: str) -> int:
        """Letters of the line outside its kept and pronounced terms."""
        if self._set_aside is not None:
            text = self._set_aside.sub("", text)
        return sum(character.isalpha() for character in text)

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
        names: dict[str, str] = {}
        """Kept terms of this line, by term, and their stand-ins."""
        stand_ins: list[_StandIn] = []

        def stand_in(match: re.Match[str]) -> str:
            term = self._kept[match.group(0)]
            if term.term not in names:
                if not free[term.female]:
                    return match.group(0)  # More kept terms in one line than stand-ins: left as is.
                name = free[term.female].pop(0)
                names[term.term] = name
                stem = _stem(name, term.female)
                pattern = rf"(?:(?<!\w)(?P<before>\w+)(?P<gap>\s+))?(?<!\w)(?P<stand_in>{stem}(?P<ending>\w*))"
                stand_ins.append(_StandIn(term, re.compile(pattern, re.IGNORECASE)))
            # A term matched in capitals is shouted, unless the glossary writes it that way ("CJ").
            name = names[term.term]
            return name.upper() if match.group(0) != term.term else name

        return Prepared(self._keep.sub(stand_in, text), tuple(stand_ins))
