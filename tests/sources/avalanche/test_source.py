"""AvalancheSource: the subtitle shown in the game, read by its line ID in the input language."""

import logging
from pathlib import Path

import pytest

from reflektortts.languages import Languages
from reflektortts.process_memory.memory import MemoryReadError
from reflektortts.process_memory.pointer import Address, PointerChain
from reflektortts.sources.avalanche.line_texts import LineTexts
from reflektortts.sources.avalanche.source import AvalancheSource
from tests.process_memory.fake_memory import FakeMemory
from tests.sources.avalanche.fake_game import CHAMPION, KILL, make_game

# MadMax.exe+10 points to the subtitle element at 0x5000; the line ID is at +8.
CHAIN = PointerChain(exe_sha256="a" * 64, base=Address("MadMax.exe", 0x10), offsets=(0x8,))
POLISH = Languages(input="pl", output="pl")
ENGLISH = Languages(input="en", output="pl")


def game(shown: int) -> dict[int, bytes]:
    return {0x140000010: (0x5000).to_bytes(8, "little"), 0x5000: bytes(8) + shown.to_bytes(4, "little")}


def show(regions: dict[int, bytes], line_id: int) -> None:
    regions[0x5000] = bytes(8) + line_id.to_bytes(4, "little")


def source_for(tmp_path: Path, regions: dict[int, bytes]) -> tuple[AvalancheSource, FakeMemory]:
    memory = FakeMemory(regions, {"madmax.exe": 0x140000000}, pointer_size=8)
    texts = LineTexts(make_game(tmp_path / "game"), background=False)
    return AvalancheSource("subtitles", 0.25, CHAIN, memory, texts), memory


def test_the_shown_line_is_read_in_the_input_language(tmp_path: Path) -> None:
    regions = game(KILL)
    source, _ = source_for(tmp_path, regions)

    assert source.read(POLISH) == "Tak jest, zabić go!"
    assert source.read(ENGLISH) == "Yeah, kill him!"
    show(regions, CHAMPION)
    assert source.read(POLISH) == "To ja zostanę czempinem!"


def test_no_subtitle_or_a_null_pointer_reads_as_nothing(tmp_path: Path) -> None:
    assert source_for(tmp_path, game(0))[0].read(POLISH) is None
    assert source_for(tmp_path, {0x140000010: bytes(8)})[0].read(POLISH) is None


def test_the_text_is_read_before_the_first_subtitle(tmp_path: Path) -> None:
    regions = game(0)
    source, _ = source_for(tmp_path, regions)
    source.read(POLISH)
    (tmp_path / "game" / "archives_win64" / "game0.arc").unlink()  # Too late to read it now.

    show(regions, KILL)

    assert source.read(POLISH) == "Tak jest, zabić go!"


def test_a_line_not_in_the_games_text_reads_as_nothing_and_is_logged_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source, _ = source_for(tmp_path, game(0x4236BED4))
    caplog.set_level(logging.INFO)

    assert source.read(POLISH) is None
    assert source.read(POLISH) is None
    assert [message for message in caplog.messages if "4236BED4" in message] == [
        "subtitles: line 4236BED4 is not in the game's text"
    ]


def test_an_unreadable_line_id_is_an_error(tmp_path: Path) -> None:
    source, _ = source_for(tmp_path, {0x140000010: (0x5000).to_bytes(8, "little")})

    with pytest.raises(MemoryReadError, match="profile may not fit this version") as raised:
        source.read(POLISH)

    assert "5008" not in str(raised.value)
    assert "5008" in str(raised.value.__cause__)


def test_close_releases_the_game_memory(tmp_path: Path) -> None:
    source, memory = source_for(tmp_path, game(0))

    source.close()

    assert memory.closed
