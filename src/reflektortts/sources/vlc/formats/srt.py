"""SubRip (.srt) subtitles.

Cues are found by their timing lines rather than by the blank lines between them: files with a
blank line missing, or one inside a cue's text, are common.
"""

import re
from collections.abc import Sequence

from reflektortts.sources.vlc.formats.cues import Cue, seconds
from reflektortts.sources.vlc.formats.markup import one_line, tags

_TIME = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
_TIMING = re.compile(rf"^\s*{_TIME}\s*-->\s*{_TIME}")
_INDEX = re.compile(r"^\s*\d+\s*$")
_TAG = tags("i", "b", "u", "s", "font")
_OVERRIDE = re.compile(r"\{\\[^}]*\}")
"""A styling code such as {\\an8}; other text in braces is kept."""


def _text(lines: Sequence[str]) -> str:
    return one_line(_OVERRIDE.sub("", _TAG.sub("", line)) for line in lines)


def parse_srt(text: str) -> list[Cue]:
    """The file's cues, in file order."""
    cues = []
    timing: tuple[float, float] | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = _TIMING.match(line)
        if match is None:
            lines.append(line)
            continue
        if lines and _INDEX.match(lines[-1]):
            lines.pop()
        if timing is not None:
            cues.append(Cue(*timing, _text(lines)))
        groups = match.groups()
        timing = (seconds(*groups[:4]), seconds(*groups[4:]))
        lines = []
    if timing is not None:
        cues.append(Cue(*timing, _text(lines)))
    return cues
