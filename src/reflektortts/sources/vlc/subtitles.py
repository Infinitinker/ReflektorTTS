"""Finds the subtitles of a media file in the input language, where VLC 3 looks for them.

VLC looks in the media's folder, then in its subfolders "subtitles" and "subs", and with its
default settings loads a file whose name is the media's (movie.srt) or the media's followed by more
words (movie.en.srt, Movie.2019.English.srt). Names are compared as whole words, lowercase,
letters and digits only: stricter than VLC, which finds the media's name anywhere in the file's,
so "Show - 1" never gets the subtitles of "Show - 10". Of these, a file is read here if one of its
extra words names the input language, or else if its name is exactly the media's; of several, the
one with the fewest extra words (movie.en.srt before movie.en.sdh.srt), and a "forced" file, which
holds only the lines in a foreign language, only if there is no other; of files alike but for
their format, the .srt. Only files in a format read here count. A file in another language
is never read as if it were in the input language, and VLC may show a different file than the one
read: which one it shows cannot be seen from outside.
"""

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.formats import Format, format_of

SUBFOLDERS = ("subtitles", "subs") if sys.platform == "win32" else ("Subtitles", "subtitles", "Subs", "subs")
"""VLC's default sub-autodetect-path; Windows ignores case in names."""
SUBTITLE_SUFFIXES = frozenset(
    f".{extension}"
    for extension in (
        "aqt ass cdg dks idx jss mpl2 mpsub pjs psb rt sami sbv scc smi srt ssa stl sub ttml tt usf vtt webvtt"
    ).split()
)
"""Every kind of subtitle file VLC loads; those in formats.FORMATS are read here."""

LANGUAGE_WORDS = {
    "en": frozenset({"en", "eng", "english"}),
    "pl": frozenset({"pl", "pol", "polish", "polski"}),
}
"""Words that name a language in subtitle file names, by ISO 639-1 code."""
LANGUAGE_NAMES = {"en": "English", "pl": "Polish"}
LEGACY_ENCODINGS = {"en": "cp1252", "pl": "cp1250"}
"""The code page subtitles in a language are usually in when they are not UTF-8."""

_WORD = re.compile(r"[^\W_]+")


def words(name: str) -> list[str]:
    """A file's name as VLC compares it: without its extension, as lowercase words."""
    stem = name.rpartition(".")[0] if "." in name else name
    return _WORD.findall(stem.lower())


@dataclass(frozen=True)
class SubtitleFile:
    """A subtitle file to read, in the format its extension names."""

    path: Path
    format: Format


FORCED = "forced"
"""The word that marks a file with only the lines in a foreign language, not all of them."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    tagged: bool
    """Whether an extra word in its name names the input language; if not, its name is exactly the media's."""
    depth: int
    """0 in the media's folder, 1 in a subfolder."""
    extra: tuple[str, ...]
    """The words of its name around the media's."""

    def rank(self) -> tuple[bool, bool, int, int, bool, str]:
        """Lowest first: a full file before a forced one, a tagged one before the exact name, the
        media's folder first, then the fewest extra words, then .srt, the most common format,
        then by name."""
        srt = self.path.suffix.lower() == ".srt"
        return (FORCED in self.extra, not self.tagged, self.depth, len(self.extra), not srt, self.path.name.lower())


def _subtitle_files(media: Path) -> Iterator[tuple[Path, int]]:
    folders = [(media.parent, 0)] + [(media.parent / name, 1) for name in SUBFOLDERS]
    seen: set[Path] = set()
    for folder, depth in folders:
        if not folder.is_dir() or folder.resolve() in seen:
            continue
        seen.add(folder.resolve())
        for path in folder.iterdir():
            if path.suffix.lower() in SUBTITLE_SUFFIXES and not path.name.startswith(".") and path != media:
                if path.is_file():
                    yield path, depth


def _extra_words(media_words: list[str], name_words: list[str]) -> tuple[str, ...] | None:
    """The words of a file's name around the media's, which must appear in it as a run of whole
    words with at least one word after it, as VLC loads by default; None if they do not."""
    size = len(media_words)
    if not size:
        return None
    for start in range(len(name_words) - size):
        if name_words[start : start + size] == media_words:
            return tuple(name_words[:start] + name_words[start + size :])
    return None


def _match(media_words: list[str], path: Path, depth: int, language: str) -> Candidate | None:
    """The file as a candidate if it is tagged with the language or named exactly as the media;
    None if it is neither, so it is not read."""
    name_words = words(path.name)
    if name_words == media_words:
        return Candidate(path, False, depth, ())
    extra = _extra_words(media_words, name_words)
    if extra is None or not LANGUAGE_WORDS.get(language, frozenset()) & set(extra):
        return None
    return Candidate(path, True, depth, extra)


def find_subtitles(media: Path, language: str) -> SubtitleFile | None:
    """The subtitle file to read for media, in the language (ISO 639-1); None if there is no subtitle
    file of any kind where VLC looks, which suits music and videos without subtitles.

    Raises VlcError, saying what to do, if there are subtitle files but none to read.
    """
    try:
        files = list(_subtitle_files(media))
    except OSError as error:
        raise VlcError(f"Cannot look for subtitles next to {media.name} ({error.strerror}).") from error
    if not files:
        return None
    media_words = words(media.name)
    candidates = [
        candidate for path, depth in files if (candidate := _match(media_words, path, depth, language)) is not None
    ]
    readable = [
        (candidate, file_format) for candidate in candidates if (file_format := format_of(candidate.path)) is not None
    ]
    if readable:
        chosen, file_format = min(readable, key=lambda pair: pair[0].rank())
        return SubtitleFile(chosen.path, file_format)
    if candidates:
        raise VlcError(
            f"{min(candidates, key=Candidate.rank).path.name} is in a format ReflektorTTS cannot read: "
            f"convert it to {media.stem}.srt."
        )
    raise VlcError(
        f"No {LANGUAGE_NAMES.get(language, language)} subtitles found: "
        f"put {media.stem}.{language}.srt or {media.stem}.srt next to {media.name}."
    )
