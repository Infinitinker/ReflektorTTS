"""LineTexts: a game's lines by ID, per language, read from its files.

Reading a language's text takes seconds, so it happens in the background the first time the
language is needed; meanwhile lines read as not known yet.
"""

import logging
import threading
import time
from pathlib import Path

from reflektortts.languages import language_name
from reflektortts.sources.avalanche.text_index import LANGUAGE_SUFFIXES, StoppedError, read_text

logger = logging.getLogger(__name__)


class UnsupportedLanguageError(Exception):
    """The game has no text in the language."""


class LineTexts:
    def __init__(self, game_dir: Path, background: bool = True) -> None:
        self._game_dir = game_dir
        self._background = background
        self._lines: dict[str, dict[int, str]] = {}
        self._reading: set[str] = set()
        self._failed: set[str] = set()
        self._error: Exception | None = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._threads: list[threading.Thread] = []

    def lines(self, language: str) -> dict[int, str] | None:
        """The game's lines in language, or None while they are being read, or if reading them
        failed. That error is raised once; the language is not read again until the game restarts.
        """
        if language not in LANGUAGE_SUFFIXES:
            names = ", ".join(sorted(language_name(code) for code in LANGUAGE_SUFFIXES))
            raise UnsupportedLanguageError(
                f"The game has no text in {language_name(language)}: set the input language to one of {names}."
            )
        with self._lock:
            start = language not in self._lines and language not in self._reading and language not in self._failed
            if start:
                self._reading.add(language)
        if start and self._background:
            thread = threading.Thread(target=self._read, args=(language,), name=f"text {language}", daemon=True)
            self._threads.append(thread)
            thread.start()
        elif start:
            self._read(language)
        with self._lock:
            error, self._error = self._error, None
            lines = self._lines.get(language)
        if error is not None:
            raise error
        return lines

    def close(self) -> None:
        self._stopped.set()
        for thread in self._threads:
            thread.join()

    def _read(self, language: str) -> None:
        started = time.monotonic()
        logger.info("Reading the game's text in %s from its files; lines are read aloud once it is done", language)
        try:
            lines = read_text(self._game_dir, language, self._stopped.is_set)
        except StoppedError:
            return
        except Exception as error:
            # Reported through lines, as sources report their failures.
            with self._lock:
                self._error = error
                self._reading.discard(language)
                self._failed.add(language)
            return
        logger.info(
            "Read %d lines in %s from the game's files in %.1f s", len(lines), language, time.monotonic() - started
        )
        with self._lock:
            self._lines[language] = lines
            self._reading.discard(language)
