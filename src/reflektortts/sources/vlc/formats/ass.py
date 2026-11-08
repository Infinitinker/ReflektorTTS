"""Advanced SubStation Alpha (.ass) and SubStation Alpha (.ssa) subtitles.

The cues are the Dialogue lines of the [Events] section, whose fields come in the order its
Format line gives; Comment lines and every other section are skipped. Text is the last field and
may hold commas. Of the text, every block in braces is left out (styling codes such as {\\i1}, or
comments), and so is everything drawn rather than written, between {\\p1} and {\\p0}.
"""

import re

from reflektortts.sources.vlc.formats.cues import Cue, seconds
from reflektortts.sources.vlc.formats.markup import one_line

_SECTION = re.compile(r"^\s*\[([^\]]*)\]\s*$")
_KEY = re.compile(r"^\s*(\w+)\s*:\s?(.*)$")
_TIME = re.compile(r"^\s*(\d+):(\d{1,2}):(\d{2})[.:](\d{1,3})\s*$")
_DEFAULT_FORMAT = ("layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text")
"""The fields when no Format line comes first: those of every .ass file and, with Marked first, of .ssa."""
_BLOCK = re.compile(r"\{([^}]*)\}")
_DRAWING = re.compile(r"\\p(\d+)")
"""Sets drawing mode: 0 ends it; any other scale starts it."""


def _plain(text: str) -> str:
    """The text without its blocks in braces and what it draws, with \\N and \\n (line breaks)
    and \\h (a hard space) as spaces."""
    parts = []
    drawing = False
    position = 0
    for block in _BLOCK.finditer(text):
        if not drawing:
            parts.append(text[position : block.start()])
        scales = _DRAWING.findall(block.group(1))
        if scales:
            drawing = int(scales[-1]) > 0
        position = block.end()
    if not drawing:
        parts.append(text[position:])
    plain = "".join(parts)
    return one_line([plain.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")])


def _time(field: str) -> float | None:
    match = _TIME.match(field)
    return None if match is None else seconds(*match.groups())


def parse_ass(text: str) -> list[Cue]:
    """The file's cues, in file order; lines whose times cannot be read are skipped."""
    cues = []
    section = ""
    fields: tuple[str, ...] = _DEFAULT_FORMAT
    for line in text.splitlines():
        if (header := _SECTION.match(line)) is not None:
            section = header.group(1).strip().lower()
            continue
        entry = _KEY.match(line)
        if section != "events" or entry is None:
            continue
        key, value = entry.group(1).lower(), entry.group(2)
        if key == "format":
            fields = tuple(name.strip().lower() for name in value.split(","))
        elif key == "dialogue":
            parts = value.split(",", len(fields) - 1)
            if len(parts) < len(fields):
                continue
            values = dict(zip(fields, parts, strict=True))
            start, end = _time(values.get("start", "")), _time(values.get("end", ""))
            if start is not None and end is not None and "text" in values:
                cues.append(Cue(start, end, _plain(values["text"])))
    return cues
