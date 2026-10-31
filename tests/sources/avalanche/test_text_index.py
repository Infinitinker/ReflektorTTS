from pathlib import Path

import pytest

from reflektortts.sources.avalanche.archives import ArchiveError
from reflektortts.sources.avalanche.text_index import StoppedError, read_text
from tests.sources.avalanche.fake_game import CHAMPION, KILL, MENU, make_game


def test_lines_come_from_bundles_and_the_patches_that_replace_them(tmp_path: Path) -> None:
    lines = read_text(make_game(tmp_path), "pl")

    assert lines == {KILL: "Tak jest, zabić go!", CHAMPION: "To ja zostanę czempinem!"}


def test_only_the_language_asked_for_is_read(tmp_path: Path) -> None:
    assert read_text(make_game(tmp_path), "en") == {KILL: "Yeah, kill him!", CHAMPION: "I'll be the champion!"}


def test_standalone_text_no_bundle_names_is_not_read(tmp_path: Path) -> None:
    assert MENU not in read_text(make_game(tmp_path), "pl")


def test_a_folder_without_archives_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="No game archives"):
        read_text(tmp_path, "pl")


def test_reading_stops_when_asked(tmp_path: Path) -> None:
    with pytest.raises(StoppedError):
        read_text(make_game(tmp_path), "pl", stopped=lambda: True)
