"""MemorySource: the text at the end of a pointer chain, decoded, and told apart from memory garbage."""

import pytest

from reflektortts.languages import Languages
from reflektortts.process_memory.memory import MemoryReadError
from reflektortts.process_memory.pointer import Address, PointerChain
from reflektortts.sources.memory.source import MemorySource, clean, decode_terminated, looks_like_text
from tests.process_memory.fake_memory import FakeMemory

CHAIN = PointerChain(exe_sha256="a" * 64, base=Address("gta2.exe", 0x10), offsets=(0x4,))
ENGLISH = Languages(input="en", output="en")


def memory_with_text(text: bytes) -> FakeMemory:
    # gta2.exe+10 points to 0x9000; the text is at 0x9000 + 4.
    return FakeMemory({0x400010: (0x9000).to_bytes(4, "little"), 0x9004: text}, {"gta2.exe": 0x400000})


def test_decode_utf16_stops_at_the_terminator() -> None:
    raw = "Hello".encode("utf-16le") + b"\0\0" + "junk".encode("utf-16le")

    assert decode_terminated(raw, "utf-16le") == "Hello"


def test_clean_turns_control_characters_into_spaces() -> None:
    assert clean(decode_terminated(b"\x01Get\nin\tthe car\x00rest", "cp1252")) == "Get in the car"


def test_decode_odd_utf16_tail_is_ignored() -> None:
    assert decode_terminated("Hi".encode("utf-16le") + b"\x41", "utf-16le") == "Hi"


def test_dialogue_in_any_supported_script_looks_like_text() -> None:
    assert looks_like_text("Welcome to the Downtown District... $50,000!")
    assert looks_like_text("Zażółć gęślą jaźń — „cytat”")
    assert looks_like_text("Привет, товарищ!")


def test_memory_garbage_does_not_look_like_text() -> None:
    assert not looks_like_text("一龥\x02\x03￿")
    assert not looks_like_text("ab\x01\x02\x03\x04\x05\x06\x07\x08")
    assert not looks_like_text("")


def test_stale_pointer_to_garbage_reads_as_no_text() -> None:
    garbage = "".join(chr(code) for code in (0x4E00, 0x3042, 0xE000, 0x0002, 0x7F00, 0x0041)).encode("utf-16le")
    source = MemorySource("messages", 0.25, "utf-16le", CHAIN, memory_with_text(garbage + b"\0\0"))

    assert source.read(ENGLISH) is None


def test_read_returns_the_text_at_the_end_of_the_chain() -> None:
    source = MemorySource(
        "messages", 0.25, "utf-16le", CHAIN, memory_with_text("Kill Frenzy!".encode("utf-16le") + b"\0\0")
    )

    assert source.read(ENGLISH) == "Kill Frenzy!"
    assert (source.name, source.poll_interval) == ("messages", 0.25)


def test_empty_text_or_null_pointer_reads_as_nothing() -> None:
    empty = MemorySource("messages", 0.25, "utf-16le", CHAIN, memory_with_text(b"\0\0"))
    null = MemorySource("messages", 0.25, "utf-16le", CHAIN, FakeMemory({0x400010: bytes(4)}, {"gta2.exe": 0x400000}))

    assert empty.read(ENGLISH) is None
    assert null.read(ENGLISH) is None


def test_unreadable_text_is_an_error() -> None:
    memory = FakeMemory({0x400010: (0x9000).to_bytes(4, "little")}, {"gta2.exe": 0x400000})

    with pytest.raises(MemoryReadError, match="profile may not fit this version") as raised:
        MemorySource("messages", 0.25, "utf-16le", CHAIN, memory).read(ENGLISH)

    # The address is for the log, which gets the cause, not for the user.
    assert "9004" not in str(raised.value)
    assert "9004" in str(raised.value.__cause__)
