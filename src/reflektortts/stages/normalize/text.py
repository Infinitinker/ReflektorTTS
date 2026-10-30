"""The language-independent part of normalization: finds abbreviations, dates, times, money,
units, percentages and numbers in a line and asks a language's Words to say them."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

# A separator followed by exactly three digits groups thousands ("50,000", "50.000",
# "50 000"); any other separator before digits is a decimal one ("12.50", "12,5").
_GROUPED = r"\d{1,3}(?:(?:,\d{3}(?!\d))+|(?:\.\d{3}(?!\d))+|(?:[  ]\d{3}(?!\d))+)"
_NUMBER = rf"(?<![\d.,])(?P<whole>{_GROUPED}|\d+)(?:[.,](?P<fraction>\d+))?"

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_AFTER = {"zł": "PLN", "PLN": "PLN", "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "€": "EUR"}

# Units that may follow the number directly ("5km", "20°C") or after a space.
UNITS = ("km", "cm", "mm", "kg", "ml", "min", "°C", "°F")
# One-letter units only count after a space, so "the 80s" stays a decade.
SHORT_UNITS = ("m", "g", "l", "h", "s")

# Dates only with a year, day first ("12.05.2024") or year first ("2024-05-12"): without one,
# "1.5." at the end of a sentence would be read as the first of May.
_DATE_DAY_FIRST = re.compile(r"(?<![\d.,])(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})(?!\d)")
_DATE_YEAR_FIRST = re.compile(r"(?<![\d-])(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?![\d-])")
_TIME = re.compile(r"(?<![\d:.,])(?P<hour>\d{1,2}):(?P<minute>\d{2})(?![\d:])")
_MONEY_BEFORE = re.compile(rf"(?P<symbol>[$€£¥])\s?{_NUMBER}")
_MONEY_AFTER = re.compile(rf"{_NUMBER}\s?(?P<code>zł|PLN|USD|EUR|GBP|JPY|€)(?!\w)")
_UNIT = re.compile(rf"{_NUMBER}(?:\s?(?P<unit>{'|'.join(UNITS)})|\s(?P<short>{'|'.join(SHORT_UNITS)}))(?![\w°])")
_PERCENT = re.compile(rf"{_NUMBER}\s?%")
_PLAIN = re.compile(_NUMBER)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.!?;:])")

# Longer runs of digits without separators are codes or phone numbers, read digit by digit.
MIN_DIGITS_READ_ONE_BY_ONE = 7


@dataclass(frozen=True)
class Number:
    whole: int
    fraction: str
    """Digits after the decimal separator, as written ("05" in "1.05"); empty if none."""
    written: str
    """The whole part as written, separators included."""

    @property
    def is_code(self) -> bool:
        return not self.fraction and self.written.isdigit() and len(self.written) >= MIN_DIGITS_READ_ONE_BY_ONE

    @property
    def cents(self) -> int:
        """The fraction as hundredths, as in money: "5" is 50, "05" is 5."""
        return int(self.fraction[:2].ljust(2, "0")) if self.fraction else 0


class Words(Protocol):
    """How one language says numbers and the things written with them."""

    def expand(self, text: str) -> str:
        """Spells out the language's abbreviations and symbols, e.g. "np." and "&"."""

    def date(self, day: int, month: int, year: int) -> str: ...

    def time(self, hour: int, minute: int) -> str:
        """A time of day on the 24-hour clock."""

    def number(self, number: Number) -> str: ...

    def money(self, currency: str, number: Number) -> str:
        """currency is an ISO 4217 code: USD, EUR, GBP, JPY or PLN."""

    def unit(self, unit: str, number: Number) -> str:
        """unit is one of UNITS or SHORT_UNITS."""

    def percent(self, number: Number) -> str: ...

    def agree(self, text: str) -> str:
        """Fixes the spelled-out line where a number depends on the words after it, e.g. Polish
        "dwa minuty" becomes "dwie minuty"."""


def _number(match: re.Match[str]) -> Number:
    written = match["whole"]
    return Number(whole=int(re.sub(r"\D", "", written)), fraction=match["fraction"] or "", written=written)


def _date(match: re.Match[str], words: Words) -> str:
    day, month, year = int(match["day"]), int(match["month"]), int(match["year"])
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return match[0]
    return f" {words.date(day, month, year)} "


def _time(match: re.Match[str], words: Words) -> str:
    hour, minute = int(match["hour"]), int(match["minute"])
    if hour > 23 or minute > 59:
        return match[0]
    return f" {words.time(hour, minute)} "


def normalize(text: str, words: Words) -> str:
    """Replaces abbreviations, dates, times, money, units, percentages and numbers with words."""
    text = words.expand(text)
    text = _DATE_DAY_FIRST.sub(lambda m: _date(m, words), text)
    text = _DATE_YEAR_FIRST.sub(lambda m: _date(m, words), text)
    text = _TIME.sub(lambda m: _time(m, words), text)
    text = _MONEY_BEFORE.sub(lambda m: f" {words.money(CURRENCY_SYMBOLS[m['symbol']], _number(m))} ", text)
    text = _MONEY_AFTER.sub(lambda m: f" {words.money(CURRENCY_AFTER[m['code']], _number(m))} ", text)
    text = _UNIT.sub(lambda m: f" {words.unit(m['unit'] or m['short'], _number(m))} ", text)
    text = _PERCENT.sub(lambda m: f" {words.percent(_number(m))} ", text)
    text = _PLAIN.sub(lambda m: f" {words.number(_number(m))} ", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    return words.agree(" ".join(text.split()))


def abbreviation_pattern(abbreviation: str) -> str:
    """A regex for an abbreviation as written, or capitalized at the start of a sentence.

    Only those spellings count, so "OK." is not taken for "ok.". Abbreviations written without
    a full stop ("dr") may have one ("dr.").
    """
    spellings = {abbreviation, abbreviation[0].upper() + abbreviation[1:]}
    dot = "" if abbreviation.endswith(".") else r"\.?"
    return rf"(?<![\w.])(?:{'|'.join(re.escape(spelling) for spelling in spellings)}){dot}(?!\w)"


def _same_case(words: str) -> Callable[[re.Match[str]], str]:
    """Replaces a match with words, capitalized if the match was."""
    return lambda match: words[0].upper() + words[1:] if match[0][0].isupper() else words


def expand_words(text: str, abbreviations: dict[str, str], symbols: dict[str, str]) -> str:
    """Replaces abbreviations (keeping a capital first letter) and symbols with words."""
    for abbreviation, words in abbreviations.items():
        text = re.sub(abbreviation_pattern(abbreviation), _same_case(words), text)
    for symbol, words in symbols.items():
        text = text.replace(symbol, f" {words} ")
    return text
