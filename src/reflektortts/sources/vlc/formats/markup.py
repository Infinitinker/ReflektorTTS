"""Turning a cue's lines of marked-up text into the one line read aloud."""

import re
from collections.abc import Iterable

_SPACES = re.compile(r"\s+")


def tags(*names: str) -> re.Pattern[str]:
    """Opening and closing tags with these names, with any attributes, classes or annotation:
    <i>, </i>, <font color="red">, <c.yellow.bg_blue>, <v Anna>. Other text in angle brackets,
    such as "<3", is not matched."""
    return re.compile(rf"</?(?:{'|'.join(names)})(?=[\s.>/])[^>]*>", re.IGNORECASE)


def one_line(lines: Iterable[str]) -> str:
    """The lines joined by spaces, with runs of whitespace as one space."""
    return _SPACES.sub(" ", " ".join(lines)).strip()
