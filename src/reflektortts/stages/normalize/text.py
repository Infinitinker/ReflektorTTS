"""The language-independent part of normalization: finds numbers, money and percentages in a
line and asks a language's Words to say them."""

import re
from dataclasses import dataclass
from typing import Protocol

# A separator followed by exactly three digits groups thousands ("50,000", "50.000",
# "50 000"); any other separator before digits is a decimal one ("12.50", "12,5").
_GROUPED = r"\d{1,3}(?:(?:,\d{3}(?!\d))+|(?:\.\d{3}(?!\d))+|(?:[  ]\d{3}(?!\d))+)"
_NUMBER = rf"(?<![\d.,])(?P<whole>{_GROUPED}|\d+)(?:[.,](?P<fraction>\d+))?"

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_AFTER = {"zł": "PLN", "PLN": "PLN", "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "€": "EUR"}

_MONEY_BEFORE = re.compile(rf"(?P<symbol>[$€£¥])\s?{_NUMBER}")
_MONEY_AFTER = re.compile(rf"{_NUMBER}\s?(?P<code>zł|PLN|USD|EUR|GBP|JPY|€)(?!\w)")
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
    """How one language says numbers."""

    def number(self, number: Number) -> str: ...

    def money(self, currency: str, number: Number) -> str:
        """currency is an ISO 4217 code: USD, EUR, GBP, JPY or PLN."""

    def percent(self, number: Number) -> str: ...

    def agree(self, text: str) -> str:
        """Fixes the spelled-out line where a number depends on the words after it, e.g. Polish
        "dwa minuty" becomes "dwie minuty"."""


def _number(match: re.Match[str]) -> Number:
    written = match["whole"]
    return Number(whole=int(re.sub(r"\D", "", written)), fraction=match["fraction"] or "", written=written)


def normalize(text: str, words: Words) -> str:
    """Replaces numbers, money and percentages with words."""
    text = _MONEY_BEFORE.sub(lambda m: f" {words.money(CURRENCY_SYMBOLS[m['symbol']], _number(m))} ", text)
    text = _MONEY_AFTER.sub(lambda m: f" {words.money(CURRENCY_AFTER[m['code']], _number(m))} ", text)
    text = _PERCENT.sub(lambda m: f" {words.percent(_number(m))} ", text)
    text = _PLAIN.sub(lambda m: f" {words.number(_number(m))} ", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    return words.agree(" ".join(text.split()))
