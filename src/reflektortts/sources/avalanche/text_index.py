"""Reads every line of a game's dialogue in one language from its archives on disk.

Text is in stringlookup files named <name>_<language suffix>.stringlookup. Dialogue is in
bundles, which name their files; a patch may replace one with a standalone file, named in the
archives only by the hash of its file name. Other standalone text, such as the menus', is not read.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from reflektortts.languages import language_name
from reflektortts.sources.avalanche.archives import Archive, ArchiveEntry, ArchiveError, damaged
from reflektortts.sources.avalanche.bundles import HEADER_SIZE, BundleError, bundle_files, is_bundle, table_size
from reflektortts.sources.avalanche.lookup3 import hashlittle
from reflektortts.sources.avalanche.stringlookup import StringLookupError, is_adf, read_stringlookup

logger = logging.getLogger(__name__)

ARCHIVE_FOLDERS = ("archives_win64", "dlc_win64", "patch_win64")
"""Folders of a game's archives, those that replace files of others last."""
LANGUAGE_SUFFIXES = {
    "de": "ger",
    "en": "eng",
    "es": "spa",
    "fr": "fre",
    "it": "ita",
    "ja": "jpn",
    "pl": "pol",
    "pt": "brp",
    "ru": "rus",
}
"""The languages of Mad Max's text (ISO 639-1) to the suffixes of its text files: mostly ISO 639-2
codes, but "brp" is Brazilian Portuguese. Spanish is "spa", the Spanish of Spain; the game's Latin
American Spanish ("nsp") is not read."""
SUFFIX = ".stringlookup"


class StoppedError(Exception):
    """Reading was stopped before it finished."""


def archive_tables(game_dir: Path) -> list[Path]:
    """The game's .tab files, those whose files replace others' last."""
    return [tab for folder in ARCHIVE_FOLDERS for tab in sorted((game_dir / folder).rglob("*.tab"))]


def read_text(game_dir: Path, language: str, stopped: Callable[[], bool] = lambda: False) -> dict[int, str]:
    """Line ID to text, for every line of dialogue in language (one of LANGUAGE_SUFFIXES)."""
    suffix = f"_{LANGUAGE_SUFFIXES[language]}{SUFFIX}"
    try:
        tabs = archive_tables(game_dir)
    except OSError as error:
        raise ArchiveError(damaged(game_dir.name)) from error
    if not tabs:
        raise ArchiveError(f"No game archives in {game_dir}: is this the game’s folder?")
    archives: list[Archive] = []
    try:
        for tab in tabs:
            archives.append(Archive(tab))
        files: dict[int, tuple[Archive, ArchiveEntry]] = {}
        tables: dict[str, dict[int, str]] = {}
        for archive in archives:
            for name_hash, entry in archive.entries.items():
                if stopped():
                    raise StoppedError
                files[name_hash] = (archive, entry)
                tables.update(_bundled_tables(archive, entry, suffix))
        for name in list(tables):
            found = files.get(hashlittle(name.encode("utf-8")))
            if found is not None:
                table = _standalone_table(*found, name)
                if table is not None:
                    tables[name] = table
        if not tables:
            raise ArchiveError(f"The game’s files have no text in {language_name(language)}: is the game complete?")
        lines: dict[int, str] = {}
        for table in tables.values():
            lines.update(table)
        return lines
    finally:
        for archive in archives:
            archive.close()


def _bundled_tables(archive: Archive, entry: ArchiveEntry, suffix: str) -> dict[str, dict[int, str]]:
    """The tables in language a bundle holds, by file name; none if the file is not a bundle."""
    header = archive.read(entry, 0, HEADER_SIZE)
    if not is_bundle(header):
        return {}
    tables = {}
    try:
        for file in bundle_files(archive.read(entry, 0, HEADER_SIZE + table_size(header))):
            name = file.name.rsplit("/", 1)[-1]
            if name.endswith(suffix):
                tables[name] = read_stringlookup(archive.read(entry, file.offset, file.size))
    except (BundleError, StringLookupError) as error:
        logger.warning("Skipping a bundle in %s: %s", archive.path, error)
    return tables


def _standalone_table(archive: Archive, entry: ArchiveEntry, name: str) -> dict[int, str] | None:
    if not is_adf(archive.read(entry, 0, 4)):
        return None
    try:
        return read_stringlookup(archive.read(entry))
    except StringLookupError as error:
        logger.warning("Skipping %s in %s: %s", name, archive.path, error)
        return None
