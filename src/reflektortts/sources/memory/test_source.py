import pytest

from reflektortts.sources.memory.fake_memory import FakeMemory
from reflektortts.sources.memory.pointer import Address
from reflektortts.sources.memory.process_memory import MemoryReadError
from reflektortts.sources.memory.source import (
    MemorySettings,
    MemorySource,
    PointerChain,
    UnsupportedGameVersion,
    decode_text,
)

GAME_HASH = "a" * 64
CHAIN = PointerChain(exe_sha256=GAME_HASH, base=Address("gta2.exe", 0x10), offsets=(0x4,))
SETTINGS = MemorySettings(encoding="utf-16le", pointers=(CHAIN,))


def memory_with_text(text: bytes) -> FakeMemory:
    # gta2.exe+10 points to 0x9000; the text is at 0x9000 + 4.
    return FakeMemory({0x400010: (0x9000).to_bytes(4, "little"), 0x9004: text}, {"gta2.exe": 0x400000})


def test_decode_utf16_stops_at_the_terminator() -> None:
    raw = "Hello".encode("utf-16le") + b"\0\0" + "junk".encode("utf-16le")

    assert decode_text(raw, "utf-16le") == "Hello"


def test_decode_turns_control_characters_into_spaces() -> None:
    assert decode_text(b"\x01Get\nin\tthe car\x00rest", "cp1252") == "Get in the car"


def test_decode_odd_utf16_tail_is_ignored() -> None:
    assert decode_text("Hi".encode("utf-16le") + b"\x41", "utf-16le") == "Hi"


def test_read_returns_the_text_at_the_end_of_the_chain() -> None:
    source = MemorySource(
        "messages", 0.25, SETTINGS, memory_with_text("Kill Frenzy!".encode("utf-16le") + b"\0\0"), GAME_HASH
    )

    assert source.read() == "Kill Frenzy!"
    assert (source.name, source.poll_interval) == ("messages", 0.25)


def test_empty_text_or_null_pointer_reads_as_nothing() -> None:
    empty = MemorySource("messages", 0.25, SETTINGS, memory_with_text(b"\0\0"), GAME_HASH)
    null = MemorySource("messages", 0.25, SETTINGS, FakeMemory({0x400010: bytes(4)}, {"gta2.exe": 0x400000}), GAME_HASH)

    assert empty.read() is None
    assert null.read() is None


def test_unreadable_text_is_an_error() -> None:
    memory = FakeMemory({0x400010: (0x9000).to_bytes(4, "little")}, {"gta2.exe": 0x400000})

    with pytest.raises(MemoryReadError, match="9004"):
        MemorySource("messages", 0.25, SETTINGS, memory, GAME_HASH).read()


def test_pointer_is_chosen_by_executable_hash_ignoring_case() -> None:
    other = PointerChain(exe_sha256="b" * 64, base=Address("gta2.exe", 0x99), offsets=())
    settings = MemorySettings(encoding="utf-16le", pointers=(other, CHAIN))
    source = MemorySource("messages", 0.25, settings, memory_with_text("Hi".encode("utf-16le")), GAME_HASH.upper())

    assert source.read() == "Hi"


def test_unknown_game_build_is_rejected_and_memory_released() -> None:
    memory = memory_with_text(b"")

    with pytest.raises(UnsupportedGameVersion, match="not supported by its profile yet"):
        MemorySource("messages", 0.25, SETTINGS, memory, "c" * 64)
    assert memory.closed
