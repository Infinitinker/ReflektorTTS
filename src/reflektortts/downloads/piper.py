"""Piper voices from their published list (rhasspy/piper-voices on Hugging Face).

The list gives each voice's files with their sizes and MD5 checksums. Licenses are not in it: each
voice's model card describes its dataset and training, so the card's text is shown as published.
Voices the installed Piper cannot run, as their config says, are not listed unless installed; a
voice whose config could not be read counts as one it can run, as nearly all are.
"""

import hashlib
import json
import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from reflektortts.downloads import http
from reflektortts.downloads.cache import cached, save
from reflektortts.downloads.source import DownloadError, DownloadPlugin, Entry, Kind, Progress
from reflektortts.languages import LANGUAGES, primary_language
from reflektortts.staging import remove_leftovers, staging_folder
from reflektortts.tts.engines.piper import SPOKEN_PHONEME_TYPES
from reflektortts.tts.voices import downloaded_voices, voice_files, voices_dir

logger = logging.getLogger(__name__)

NAME = "piper"
TITLE = "Piper"
REPOSITORY = "https://huggingface.co/rhasspy/piper-voices"
INDEX_URL = f"{REPOSITORY}/resolve/main/voices.json"
FILE_URL = f"{REPOSITORY}/resolve/main/"
PAGE_URL = f"{REPOSITORY}/tree/main/"
VOICE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
"""A voice's name becomes its file names, so it may not lead out of the voices folder."""


class PiperVoices:
    def __init__(
        self,
        cache: Path,
        voices: Path | None = None,
        fetch: Callable[[str], bytes] = http.fetch,
        download: Callable[[str, Path, Progress], None] = http.download,
    ) -> None:
        self._cache = cache
        self._voices = voices or voices_dir()
        self._fetch = fetch
        self._download = download
        remove_leftovers(self._voices)

    def entries(self, refresh: bool) -> list[Entry]:
        voices = self._index(refresh)
        cards = self._details("model-cards.json", voices, refresh, "MODEL_CARD", _card)
        types = self._details("phoneme-types.json", voices, refresh, ".onnx.json", _phoneme_type)
        installed = set(downloaded_voices(self._voices))
        return [
            self._entry(key, info, cards.get(key), key in installed)
            for key, info in sorted(voices.items())
            if key in installed or types.get(key, "espeak") in SPOKEN_PHONEME_TYPES
        ]

    def download(self, entry: Entry, progress: Progress) -> None:
        key = entry.id.removeprefix(f"{NAME}:")
        files = _voice_files(self._index(refresh=False)[key])
        total = sum(file["size_bytes"] for file in files.values())
        self._voices.mkdir(parents=True, exist_ok=True)
        # Downloading into a staging folder means an interrupted download never leaves a broken voice.
        with staging_folder(self._voices) as staging:
            done = 0

            def overall(size: int, _file_total: int | None) -> None:
                progress(done + size, total)

            for name, (path, file) in zip(voice_files(key), files.items(), strict=True):
                target = Path(staging) / name
                self._download(FILE_URL + path, target, overall)
                if hashlib.md5(target.read_bytes()).hexdigest() != file["md5_digest"]:
                    raise DownloadError(f"The downloaded voice {key} is damaged. Try again.")
                done += file["size_bytes"]
            for name in voice_files(key):
                (Path(staging) / name).replace(self._voices / name)

    def remove(self, entry: Entry) -> None:
        for name in voice_files(entry.id.removeprefix(f"{NAME}:")):
            (self._voices / name).unlink(missing_ok=True)

    def _index(self, refresh: bool) -> dict[str, Any]:
        """The voices in languages ReflektorTTS knows, by name; a name that cannot be a file name is
        skipped."""
        data = cached(self._cache / "voices.json", lambda: self._fetch(INDEX_URL), refresh)
        try:
            index = json.loads(data)
            voices = {key: info for key, info in index.items() if _language(info) in LANGUAGES}
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise DownloadError(f"The list of Piper voices is not in the expected format ({error}).") from error
        for key in [key for key in voices if not VOICE_NAME.fullmatch(key)]:
            logger.warning("Skipping the Piper voice %r: its name cannot be a file name", key)
            del voices[key]
        return voices

    def _details(
        self, cache: str, voices: dict[str, Any], refresh: bool, suffix: str, read: Callable[[bytes], str]
    ) -> dict[str, str]:
        """Something read from one file of each voice (the file whose path ends in suffix), kept in
        the cache file of that name with the file's checksum. Files are fetched on a refresh, only
        those whose checksum in the list has changed, and the first time, when nothing was read
        yet; so listing again, e.g. after each download, never waits on the internet. A file that
        cannot be fetched keeps what was read before; once one fails for a reason other than not being
        there, such as a lost connection, the rest are not tried."""
        path = self._cache / cache
        saved = _saved_details(path)
        files = {key: found for key, info in voices.items() if (found := _file(info, suffix)) is not None}
        if refresh or not path.is_file():
            stale = {key: file for key, file in files.items() if key not in saved or saved[key][0] != _digest(file)}
            failed = threading.Event()

            def fetched(file: tuple[str, dict[str, Any]]) -> list[str] | None:
                if failed.is_set():
                    return None
                try:
                    return [_digest(file), read(self._fetch(FILE_URL + file[0]))]
                except http.NotFoundError as error:
                    logger.debug("%s", error)
                    return None
                except DownloadError as error:
                    failed.set()
                    logger.debug("Could not fetch %s: %s", file[0], error)
                    return None

            results = http.each(fetched, stale.values())
            read_now = {key: value for key, value in zip(stale, results, strict=True) if value}
            if read_now or not path.is_file():
                saved = saved | read_now
                save(path, json.dumps(saved, ensure_ascii=False).encode("utf-8"))
        return {key: value for key, (_digest_read, value) in saved.items()}

    def _entry(self, key: str, info: dict[str, Any], card: str | None, installed: bool) -> Entry:
        files = _voice_files(info)
        model = next(iter(files))
        return Entry(
            id=f"{NAME}:{key}",
            source_title=TITLE,
            kind=Kind.VOICE,
            name=key,
            languages=(_language(info),),
            size=sum(file["size_bytes"] for file in files.values()),
            license=card,
            page=PAGE_URL + str(PurePosixPath(model).parent),
            installed=installed,
        )


def _language(info: dict[str, Any]) -> str:
    """The voice's language, as a code here: Norwegian voices ("no") speak Bokmål ("nb")."""
    return primary_language(str(info["language"]["family"]))


def _file(info: dict[str, Any], suffix: str) -> tuple[str, dict[str, Any]] | None:
    """The voice's file whose path ends in suffix, with its size and checksum."""
    return next(((path, file) for path, file in info["files"].items() if path.endswith(suffix)), None)


def _digest(file: tuple[str, dict[str, Any]]) -> str:
    return str(file[1].get("md5_digest", ""))


def _saved_details(path: Path) -> dict[str, list[str]]:
    """The details read before, as checksum and value by voice; those not in that form are left
    out, to be read again."""
    try:
        saved = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except ValueError:
        return {}
    if not isinstance(saved, dict):
        return {}
    return {key: value for key, value in saved.items() if isinstance(value, list) and len(value) == 2}


def _card(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _phoneme_type(data: bytes) -> str:
    """How the voice turns text into sounds, as its config says; Piper's default if it does not."""
    try:
        return str(json.loads(data).get("phoneme_type", "espeak"))
    except (ValueError, AttributeError):
        return "espeak"


def _voice_files(info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The voice's model and its config, in that order, by path in the repository."""
    files: dict[str, dict[str, Any]] = info["files"]
    model = next(path for path in files if path.endswith(".onnx"))
    config = next(path for path in files if path.endswith(".onnx.json"))
    return {model: files[model], config: files[config]}


PLUGIN = DownloadPlugin(name=NAME, create=PiperVoices)
