import time
from collections.abc import Callable
from pathlib import Path

import pytest

from reflektortts.sources.avalanche import line_texts
from reflektortts.sources.avalanche.archives import ArchiveError
from reflektortts.sources.avalanche.line_texts import LineTexts, UnsupportedLanguageError
from reflektortts.sources.avalanche.text_index import read_text
from tests.sources.avalanche.fake_game import KILL, make_game


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Counts readings of the game's files, by language."""
    done: list[str] = []

    def counting(game_dir: Path, language: str, stopped: Callable[[], bool]) -> dict[int, str]:
        done.append(language)
        return read_text(game_dir, language, stopped)

    monkeypatch.setattr(line_texts, "read_text", counting)
    return done


def test_a_languages_lines_are_read_once(tmp_path: Path, reads: list[str]) -> None:
    texts = LineTexts(make_game(tmp_path), background=False)

    lines = texts.lines("pl")
    texts.lines("pl")
    texts.lines("en")

    assert lines is not None and lines[KILL] == "Tak jest, zabić go!"
    assert reads == ["pl", "en"]


def test_a_failed_reading_is_reported_once_and_not_repeated(tmp_path: Path, reads: list[str]) -> None:
    texts = LineTexts(tmp_path, background=False)

    with pytest.raises(ArchiveError, match="No game archives"):
        texts.lines("pl")
    assert texts.lines("pl") is None
    assert reads == ["pl"]


def test_a_language_the_game_has_no_text_in_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedLanguageError, match='no text in "xx"'):
        LineTexts(tmp_path, background=False).lines("xx")


def test_lines_are_read_in_the_background(tmp_path: Path) -> None:
    texts = LineTexts(make_game(tmp_path))
    deadline = time.monotonic() + 5
    lines = texts.lines("pl")
    while lines is None and time.monotonic() < deadline:
        time.sleep(0.01)
        lines = texts.lines("pl")
    texts.close()

    assert lines is not None and lines[KILL] == "Tak jest, zabić go!"
