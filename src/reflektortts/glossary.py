"""A profile's glossary: words and phrases of its app that translation and speech treat specially."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    """As the app writes it, e.g. "Big Smoke"."""
    keep: bool = False
    """Never translated, e.g. a name that is also a word ("Sweet")."""
    female: bool = False
    """A kept term is a woman's name, so translation declines it as one."""
    means: str | None = None
    """Plain words in the input language the term is translated as, e.g. "neighborhood" for "hood"."""
    pronounce: Mapping[str, str] = field(default_factory=dict)
    """How the term is pronounced, by output language (ISO 639-1), e.g. {"pl": "Karl"} for "Carl"."""
    other_spellings: tuple[str, ...] = ()
    """Other ways the app writes the term, e.g. "Big smoke"."""

    @property
    def spellings(self) -> tuple[str, ...]:
        return (self.term, *self.other_spellings)


type Glossary = tuple[GlossaryTerm, ...]
type Glossaries = Mapping[str, Glossary]
"""A profile's glossaries, by the input language (ISO 639-1) their terms are written in: a line
read in another language gets none, as terms of one language turn another into gibberish."""


class TermFinder:
    """Finds glossary terms in a text: in any of their spellings, and in capitals, as in shouted
    lines. A spelling the glossary itself writes in capitals ("CJ") is not shouted."""

    def __init__(self, terms: Iterable[GlossaryTerm]) -> None:
        self._terms: dict[str, GlossaryTerm] = {}
        for term in terms:
            for spelling in term.spellings:
                self._terms[spelling] = term
        for spelling, term in list(self._terms.items()):
            self._terms.setdefault(spelling.upper(), term)
        longest_first = sorted(self._terms, key=len, reverse=True)
        self.alternation = "|".join(map(re.escape, longest_first))
        """A regular expression matching any of the terms, as they may be written."""

    def __bool__(self) -> bool:
        return bool(self._terms)

    def found(self, matched: str) -> tuple[GlossaryTerm, bool]:
        """The term matched, with the spelling the text uses as its term, and whether it is shouted."""
        term = self._terms[matched]
        spelling = next(spelling for spelling in term.spellings if matched in (spelling, spelling.upper()))
        others = tuple(other for other in term.spellings if other != spelling)
        return replace(term, term=spelling, other_spellings=others), matched != spelling

    def whole_words(self) -> re.Pattern[str] | None:
        """Matches the terms as whole words; None if there are none."""
        return re.compile(rf"(?<!\w)(?:{self.alternation})(?!\w)") if self else None
