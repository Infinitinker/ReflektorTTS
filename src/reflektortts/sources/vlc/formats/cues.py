"""Subtitle cues, whatever their file's format, and the one shown at a moment."""

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import groupby


@dataclass(frozen=True)
class Cue:
    start: float
    """Seconds into the media."""
    end: float
    text: str


class Cues:
    """A file's cues, by start time."""

    def __init__(self, cues: Sequence[Cue]) -> None:
        self.cues = tuple(sorted(cues, key=lambda cue: cue.start))
        self._starts = [cue.start for cue in self.cues]

    def __len__(self) -> int:
        return len(self.cues)

    def at(self, seconds: float) -> str | None:
        """The text of the cue shown at seconds, or None. Of cues that overlap, the one that
        started last: the tracker would repeat a line if they were joined as they come and go."""
        index = bisect.bisect_right(self._starts, seconds) - 1
        if index < 0 or self.cues[index].end <= seconds:
            return None
        return self.cues[index].text


def seconds(hours: str | None, minutes: str, secs: str, fraction: str) -> float:
    """A timestamp's parts as seconds; the fraction's digits are its first decimals, so "5" and
    "50" are half a second, as in "0,5" or ASS's centiseconds."""
    whole = int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)
    return whole + int(fraction.ljust(3, "0")[:3]) / 1000


def collect(cues: Iterable[Cue]) -> Cues:
    """The cues to read: by start time, without those whose end is not after their start or that
    have no text, and those that start together as one, their texts in file order and each only
    once, until the last of them ends. Files converted from other formats often split a moment's
    lines into cues by speaker or position, ASS files draw a line again on another layer for its
    border or glow, and only one cue is shown at a time."""
    kept = sorted((cue for cue in cues if cue.end > cue.start and cue.text), key=lambda cue: cue.start)
    merged = []
    for start, group in groupby(kept, key=lambda cue: cue.start):
        together = list(group)
        texts = dict.fromkeys(cue.text for cue in together)
        merged.append(Cue(start, max(cue.end for cue in together), " ".join(texts)))
    return Cues(merged)
