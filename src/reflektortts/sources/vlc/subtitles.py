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
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from reflektortts.languages import LANGUAGES, alias_names, language_name, other_codes
from reflektortts.letters import WORD
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

DEFAULT_ENCODING = "cp1252"
"""The code page of subtitles that are not UTF-8, in a language whose text is Unicode only."""


APOSTROPHES = str.maketrans("", "", "'‘’ʻʼ`")
"""Apostrophes, left out of language names, so "O‘zbek" names Uzbek as "Ozbek"."""
REGION = re.compile(r"(?<![^\W_])([a-z]{2,3})[-_]([a-z]{2})(?![^\W_])")
"""A language code with its region, as in "pt-BR" or "pt_BR"; regions such as BR (Breton) are
language codes too."""
HEARING_IMPAIRED = "hi"
"""Marks subtitles for the hearing-impaired ("movie.en.hi.srt") more often than it names Hindi, so
it names Hindi only when nothing else in the name names a language."""


def words(name: str) -> list[str]:
    """A file's name as VLC compares it: without its extension, as lowercase words."""
    stem = name.rpartition(".")[0] if "." in name else name
    return WORD.findall(unicodedata.normalize("NFC", stem).lower())


@cache
def _languages_named() -> dict[str, str]:
    """The language each word names in file names: a language's codes, and the words of its
    English and own names, also without accents ("de", "ger", "deu", "german", "deutsch";
    "francais"). A word of several languages' names names none, unless it is another language's
    code ("yi" is Yiddish, not Sichuan Yi) or the name of a language known by another's code
    ("norwegian" and "norsk" are Bokmål, not Nynorsk). Single letters name nothing."""
    codes: dict[str, str] = {}
    preferred: dict[str, str] = {}
    names: dict[str, set[str]] = {}
    for code, language in LANGUAGES.items():
        for word in (code, language.iso639_2b, language.iso639_2t, *other_codes(code)):
            codes[word] = code
        for word in _name_words(*alias_names(code)):
            preferred[word] = code
        for word in _name_words(language.english_name, language.name):
            names.setdefault(word, set()).add(code)
    unique = {word: next(iter(found)) for word, found in names.items() if len(found) == 1}
    return unique | preferred | codes


def _name_words(*names: str) -> set[str]:
    found = {word for name in names for word in words(f"{name.translate(APOSTROPHES)}.") if len(word) > 1}
    return found | {plain for word in found if (plain := _without_accents(word)).isascii()}


def _languages_in(extra: tuple[str, ...], regions: set[tuple[str, str]]) -> set[str]:
    """The languages a file's extra words name, leaving out the regions after language codes."""
    named = _languages_named()
    extra = tuple(word for index, word in enumerate(extra) if index == 0 or (extra[index - 1], word) not in regions)
    found = {named[word] for word in extra if word in named and word != HEARING_IMPAIRED}
    if not found and HEARING_IMPAIRED in extra:
        found.add(named[HEARING_IMPAIRED])
    return found


def legacy_encoding(code: str) -> str:
    """The code page subtitles in the language are usually in when they are not UTF-8."""
    language = LANGUAGES.get(code)
    return language.code_page if language is not None and language.code_page else DEFAULT_ENCODING


def _without_accents(word: str) -> str:
    return "".join(letter for letter in unicodedata.normalize("NFKD", word) if not unicodedata.combining(letter))


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
    """The file as a candidate if it is tagged with the language and no other, or named exactly as
    the media; None if it is neither, so it is not read."""
    name_words = words(path.name)
    if name_words == media_words:
        return Candidate(path, False, depth, ())
    extra = _extra_words(media_words, name_words)
    regions = set(REGION.findall(unicodedata.normalize("NFC", path.name).lower()))
    if extra is None or _languages_in(extra, regions) != {language}:
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
            f"{min(candidates, key=Candidate.rank).path.name} is in a format that cannot be read: "
            f"convert it to {media.stem}.srt."
        )
    raise VlcError(
        f"No {language_name(language)} subtitles found: "
        f"put {media.stem}.{language}.srt or {media.stem}.srt next to {media.name}."
    )
