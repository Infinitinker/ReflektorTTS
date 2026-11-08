"""Fitting text into a fixed number of lines, so a long text never pushes what is below it."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import chain, islice

ELLIPSIS = "…"


@dataclass(frozen=True)
class FittedText:
    lines: list[str]
    """At most the lines asked for; the last one ends with an ellipsis if the text was cut."""
    cut: bool


def fit_lines(text: str, width: int, measure: Callable[[str], int], max_lines: int) -> FittedText:
    """Wraps text at spaces into lines at most width pixels wide, as measure says, breaking a word
    too long for a line (a file name, a hash) where the line ends. Text that needs more than
    max_lines (at least 1) is cut, its last line ending with an ellipsis. Only the lines kept are
    measured, so a long text costs no more than a short one."""
    paragraphs = text.strip().split("\n")
    wrapped = chain.from_iterable(_wrap(paragraph, width, measure) for paragraph in paragraphs)
    lines = list(islice(wrapped, max_lines + 1))
    if len(lines) <= max_lines:
        return FittedText(lines, cut=False)
    kept = lines[:max_lines]
    kept[-1] = _with_ellipsis(kept[-1], width, measure)
    return FittedText(kept, cut=True)


def _wrap(paragraph: str, width: int, measure: Callable[[str], int]) -> Iterator[str]:
    line = ""
    for word in paragraph.split():
        candidate = f"{line} {word}" if line else word
        if measure(candidate) <= width:
            line = candidate
            continue
        if measure(word) <= width:
            yield line
            line = word
            continue
        # Too long for any line: it starts right here and is broken where the lines end.
        line = candidate
        while measure(line) > width and len(line) > 1:
            split = _longest_fitting(line, width, measure)
            yield line[:split].rstrip()
            line = line[split:].lstrip()
    yield line


def _longest_fitting(text: str, width: int, measure: Callable[[str], int]) -> int:
    """How many of text's first characters fit in width; at least one, so wrapping always ends."""
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle]) <= width:
            low = middle
        else:
            high = middle - 1
    return low


def _with_ellipsis(line: str, width: int, measure: Callable[[str], int]) -> str:
    kept = line.rstrip()
    while kept and measure(kept + ELLIPSIS) > width:
        kept = kept[:-1].rstrip()
    return kept + ELLIPSIS
