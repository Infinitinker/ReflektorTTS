"""Piper voices from their published list (rhasspy/piper-voices on Hugging Face).

The list gives each voice's files with their sizes and MD5 checksums. Licenses are not in it: each
voice's model card describes its dataset and training, so the card's text is shown as published.
"""

import hashlib
import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from reflektortts.downloads import http
from reflektortts.downloads.cache import cached, save
from reflektortts.downloads.source import DownloadError, DownloadPlugin, Entry, Kind, Progress
from reflektortts.languages import LANGUAGES
from reflektortts.tts.voices import downloaded_voices, voice_files, voices_dir

logger = logging.getLogger(__name__)

NAME = "piper"
TITLE = "Piper"
REPOSITORY = "https://huggingface.co/rhasspy/piper-voices"
INDEX_URL = f"{REPOSITORY}/resolve/main/voices.json"
FILE_URL = f"{REPOSITORY}/resolve/main/"
PAGE_URL = f"{REPOSITORY}/tree/main/"


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

    def entries(self, refresh: bool) -> list[Entry]:
        voices = self._index(refresh)
        cards = self._cards(voices)
        installed = set(downloaded_voices(self._voices))
        return [self._entry(key, info, cards.get(key), key in installed) for key, info in sorted(voices.items())]

    def download(self, entry: Entry, progress: Progress) -> None:
        key = entry.id.removeprefix(f"{NAME}:")
        files = _voice_files(self._index(refresh=False)[key])
        total = sum(file["size_bytes"] for file in files.values())
        self._voices.mkdir(parents=True, exist_ok=True)
        # Downloading into a staging folder means an interrupted download never leaves a broken voice.
        with tempfile.TemporaryDirectory(dir=self._voices) as staging:
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
        """The voices in the languages ReflektorTTS supports, by name."""
        data = cached(self._cache / "voices.json", lambda: self._fetch(INDEX_URL), refresh)
        try:
            index = json.loads(data)
            return {key: info for key, info in index.items() if info["language"]["family"] in LANGUAGES}
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise DownloadError(f"The list of Piper voices is not in the expected format ({error}).") from error

    def _cards(self, voices: dict[str, Any]) -> dict[str, str]:
        """Each voice's model card; cards are fetched once and kept, since they hardly change."""
        path = self._cache / "model-cards.json"
        cards: dict[str, str] = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        fetched = False
        for key, info in voices.items():
            card = next((name for name in info["files"] if name.endswith("MODEL_CARD")), None)
            if key in cards or card is None:
                continue
            try:
                cards[key] = self._fetch(FILE_URL + card).decode("utf-8", errors="replace").strip()
                fetched = True
            except DownloadError as error:
                logger.debug("No model card for %s: %s", key, error)
        if fetched:
            save(path, json.dumps(cards, ensure_ascii=False).encode("utf-8"))
        return cards

    def _entry(self, key: str, info: dict[str, Any], card: str | None, installed: bool) -> Entry:
        files = _voice_files(info)
        model = next(iter(files))
        return Entry(
            id=f"{NAME}:{key}",
            source_title=TITLE,
            kind=Kind.VOICE,
            name=key,
            languages=(info["language"]["family"],),
            size=sum(file["size_bytes"] for file in files.values()),
            license=card,
            page=PAGE_URL + str(PurePosixPath(model).parent),
            installed=installed,
        )


def _voice_files(info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The voice's model and its config, in that order, by path in the repository."""
    files: dict[str, dict[str, Any]] = info["files"]
    model = next(path for path in files if path.endswith(".onnx"))
    config = next(path for path in files if path.endswith(".onnx.json"))
    return {model: files[model], config: files[config]}


PLUGIN = DownloadPlugin(name=NAME, create=PiperVoices)
