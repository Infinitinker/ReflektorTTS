"""YouTube SubViewer (.sbv) subtitles: each cue a timing line, "0:00:01.000,0:00:04.000", then
its text, until a blank line or, where that is missing, the next timing line. Lines outside a cue
are skipped."""

import re

from reflektortts.sources.vlc.formats.cues import Cue, seconds
from reflektortts.sources.vlc.formats.markup import one_line

_TIME = r"(\d+):(\d{1,2}):(\d{2})[.,](\d{1,3})"
_TIMING = re.compile(rf"^\s*{_TIME}\s*,\s*{_TIME}\s*$")


def parse_sbv(text: str) -> list[Cue]:
    """The file's cues, in file order."""
    cues = []
    timing: tuple[float, float] | None = None
    lines: list[str] = []
    for line in [*text.splitlines(), ""]:
        match = _TIMING.match(line)
        if timing is not None and (match is not None or not line.strip()):
            cues.append(Cue(*timing, one_line(lines)))
            timing, lines = None, []
        if match is not None:
            groups = match.groups()
            timing = (seconds(*groups[:4]), seconds(*groups[4:]))
        elif timing is not None:
            lines.append(line)
    return cues
