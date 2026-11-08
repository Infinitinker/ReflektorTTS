"""The subtitle formats read, and reading a file's cues in the one its extension names."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reflektortts.sources.vlc.formats.ass import parse_ass
from reflektortts.sources.vlc.formats.cues import Cue, Cues, collect
from reflektortts.sources.vlc.formats.sbv import parse_sbv
from reflektortts.sources.vlc.formats.srt import parse_srt
from reflektortts.sources.vlc.formats.vtt import parse_vtt


@dataclass(frozen=True)
class Format:
    name: str
    """For messages: "the {name} format"."""
    parse: Callable[[str], list[Cue]]
    """The cues of a file's text, in file order, as written."""


_VTT = Format("WebVTT", parse_vtt)
FORMATS = {
    ".srt": Format("SubRip (.srt)", parse_srt),
    ".vtt": _VTT,
    ".webvtt": _VTT,
    ".ass": Format("Advanced SubStation Alpha (.ass)", parse_ass),
    ".ssa": Format("SubStation Alpha (.ssa)", parse_ass),
    ".sbv": Format("SubViewer (.sbv)", parse_sbv),
}
"""By file extension, lowercase: every one VLC loads that is read here."""


def format_of(path: Path) -> Format | None:
    """The format the file's extension names, if it is read."""
    return FORMATS.get(path.suffix.lower())


def decode(data: bytes, fallback: str) -> str:
    """The text of a subtitle file: UTF-8 or UTF-16 as their byte order marks say, else UTF-8 if
    it is valid, else the fallback, a legacy code page such as cp1250."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(fallback, errors="replace")


def read_cues(file_format: Format, data: bytes, fallback: str) -> Cues:
    """The cues to read in a file's data; text that is not UTF-8 or UTF-16 is in the fallback
    encoding."""
    return collect(file_format.parse(decode(data, fallback)))
