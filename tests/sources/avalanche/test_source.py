import logging

import pytest

from reflektortts.process_memory.memory import MemoryReadError
from reflektortts.process_memory.pointer import Address, PointerChain
from reflektortts.sources.avalanche.source import AvalancheSource
from tests.process_memory.fake_memory import FakeMemory

KILL = 0xAFA0D59E
CHAMPION = 0x838A371D
# MadMax.exe+10 points to the subtitle element at 0x5000; the line ID is at +8.
CHAIN = PointerChain(exe_sha256="a" * 64, base=Address("MadMax.exe", 0x10), offsets=(0x8,))


def game(shown: int) -> dict[int, bytes]:
    return {0x140000010: (0x5000).to_bytes(8, "little"), 0x5000: bytes(8) + shown.to_bytes(4, "little")}


def show(regions: dict[int, bytes], line_id: int) -> None:
    regions[0x5000] = bytes(8) + line_id.to_bytes(4, "little")


def source_for(regions: dict[int, bytes]) -> tuple[AvalancheSource, FakeMemory]:
    memory = FakeMemory(regions, {"madmax.exe": 0x140000000}, pointer_size=8)
    return AvalancheSource("subtitles", 0.25, CHAIN, memory), memory


def test_each_shown_line_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    regions = game(KILL)
    source, _ = source_for(regions)
    caplog.set_level(logging.INFO)

    source.read()
    source.read()
    show(regions, 0)
    source.read()
    show(regions, CHAMPION)
    source.read()

    assert caplog.messages == ["subtitles: line AFA0D59E shown", "subtitles: line 838A371D shown"]


def test_the_text_is_not_read_yet() -> None:
    source, _ = source_for(game(KILL))

    assert source.read() is None


def test_a_null_pointer_means_no_subtitle(caplog: pytest.LogCaptureFixture) -> None:
    source, _ = source_for({0x140000010: bytes(8)})
    caplog.set_level(logging.INFO)

    assert source.read() is None
    assert caplog.messages == []


def test_an_unreadable_line_id_is_an_error() -> None:
    source, _ = source_for({0x140000010: (0x5000).to_bytes(8, "little")})

    with pytest.raises(MemoryReadError, match="5008"):
        source.read()


def test_close_releases_the_game_memory() -> None:
    source, memory = source_for(game(0))

    source.close()

    assert memory.closed
