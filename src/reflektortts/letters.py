"""Letters and words of text in any script.

Python's \\w and str.isalpha() leave out the vowel signs and other marks that scripts such as
Hindi's and Thai's write as characters of their own, so a word like "राम" seems to end in the middle
of "रामू". The helpers here count those marks as part of the word.
"""

import re
import sys
import unicodedata

# Planes 0 and 1 hold every script with marks, and plane 14 the variation selectors; the rest has none.
_PLANES_WITH_MARKS = (range(0x20000), range(0xE0000, 0xE1000))


def _mark_ranges() -> str:
    """The combining marks, as ranges for a character class."""
    ranges: list[str] = []
    start: int | None = None
    for plane in _PLANES_WITH_MARKS:
        for code in [*plane, sys.maxunicode + 1]:
            is_mark = code <= sys.maxunicode and unicodedata.category(chr(code)).startswith("M")
            if is_mark and start is None:
                start = code
            elif not is_mark and start is not None:
                ranges.append(f"\\U{start:08x}-\\U{code - 1:08x}")
                start = None
    return "".join(ranges)


WORD_CHARACTER = rf"[\w{_mark_ranges()}]"
"""A regular expression for a character of a word: a letter, digit or underscore, or a mark."""

_LATIN = r"a-zA-Z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff"
LATIN_LETTER = f"[{_LATIN}]"
"""A letter of the Latin alphabet, as names and words from English-speaking apps are written in."""
LATIN_WORD_CHARACTER = rf"[0-9{_LATIN}\u0300-\u036f\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]"
"""A letter of the Latin alphabet, its accents, or a digit, also in the full-width forms Chinese and
Japanese text writes them in ("ＡＬ")."""

WORD = re.compile(rf"(?:(?!_){WORD_CHARACTER})+")
"""A word: a run of letters, digits and marks."""


def is_mark(character: str) -> bool:
    return unicodedata.category(character).startswith("M")


def letter_count(text: str) -> int:
    """The letters in text, counting the vowel signs and other marks: "हूँ" has three."""
    return sum(character.isalpha() or is_mark(character) for character in text)


def ends_in_letter(text: str) -> bool:
    """Whether the text ends in a letter, digit or mark, rather than punctuation."""
    return bool(text) and (text[-1].isalnum() or is_mark(text[-1]))
