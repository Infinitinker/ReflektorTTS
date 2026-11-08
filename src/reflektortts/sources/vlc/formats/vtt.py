"""WebVTT (.vtt, .webvtt) subtitles.

A file starts with the line WEBVTT, as VLC requires, and holds blocks separated by blank lines:
a cue (an optional identifier line, a timing line, its text), or a NOTE, STYLE or REGION block,
which is skipped, as is any other block without a timing line.
"""

import html
import re
from collections.abc import Iterator, Sequence

from reflektortts.sources.vlc.formats.cues import Cue, seconds
from reflektortts.sources.vlc.formats.markup import one_line

_HEADER = re.compile(r"^WEBVTT(?:[ \t]|$)")
_SKIPPED = re.compile(r"^(?:NOTE|STYLE|REGION)(?:[ \t]|$)")
_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
_TIMING = re.compile(rf"^\s*{_TIME}\s*-->\s*{_TIME}(?:\s|$)")
"""A timing line; cue settings such as "align:start line:0" may follow the end time."""
_RUBY_TEXT = re.compile(r"<rt(?=[\s.>])[^>]*>.*?(?:</rt\s*>|(?=</ruby)|$)", re.IGNORECASE | re.DOTALL)
"""A reading annotation over ruby base text (<ruby>漢<rt>kan</rt></ruby>), which would read the word twice."""
_TAG = re.compile(r"<[^>]*>")
"""Any tag, such as <v Anna>, <c.yellow>, <i>, <font color=red> or a karaoke timestamp
<00:00:02.000>: in a cue's text, a "<" that is not one is written "&lt;"."""
_DIRECTION_MARKS = str.maketrans("", "", chr(0x200E) + chr(0x200F))
"""&lrm; and &rlm;, which only order right-to-left text."""


def _blocks(lines: Sequence[str]) -> Iterator[list[str]]:
    block: list[str] = []
    for line in lines:
        if line.strip():
            block.append(line)
        elif block:
            yield block
            block = []
    if block:
        yield block


def _text(lines: Sequence[str]) -> str:
    text = _TAG.sub("", _RUBY_TEXT.sub("", "\n".join(lines)))
    return one_line([html.unescape(text).translate(_DIRECTION_MARKS)])


def _cue(block: list[str]) -> Cue | None:
    if _SKIPPED.match(block[0]):
        return None
    for index in (0, 1):  # A cue's identifier line may come before its timing line.
        match = _TIMING.match(block[index]) if index < len(block) else None
        if match is not None:
            groups = match.groups()
            return Cue(seconds(*groups[:4]), seconds(*groups[4:]), _text(block[index + 1 :]))
    return None


def _cue_blocks(lines: Sequence[str]) -> Iterator[list[str]]:
    """The blocks after the header, the WEBVTT line and any metadata lines after it. A timing line
    ends the header too, as it does for VLC, and starts the first cue."""
    blocks = _blocks(lines)
    header = next(blocks)
    for index, line in enumerate(header[1:], 1):
        if "-->" in line:
            yield header[index:]
            break
    yield from blocks


def parse_vtt(text: str) -> list[Cue]:
    """The file's cues, in file order; none if it does not start with WEBVTT."""
    lines = text.splitlines()
    if not lines or not _HEADER.match(lines[0]):
        return []
    return [cue for block in _cue_blocks(lines) if (cue := _cue(block)) is not None]
