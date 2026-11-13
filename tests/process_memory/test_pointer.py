"""Pointer chains in Cheat Engine notation: parsing them, picking one by the executable's hash, and following it."""

import pytest

from reflektortts.process_memory.memory import MemoryReadError, ProcessMemoryError
from reflektortts.process_memory.pointer import (
    Address,
    PointerChain,
    UnsupportedAppVersion,
    chain_for,
    parse_address,
    parse_pointer_chains,
    resolve,
)
from tests.process_memory.fake_memory import FakeMemory


def pointer(value: int) -> bytes:
    return value.to_bytes(4, "little")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("gta2.exe+272F40", Address("gta2.exe", 0x272F40)),
        ("4A2F40", Address(None, 0x4A2F40)),
        (" app.exe+ff ", Address("app.exe", 0xFF)),
    ],
)
def test_parse_address(text: str, expected: Address) -> None:
    assert parse_address(text) == expected


@pytest.mark.parametrize("text", ["", "gta2.exe+", "+12", "gta2.exe+XYZ"])
def test_parse_address_rejects_bad_text(text: str) -> None:
    with pytest.raises(ValueError, match="is not an address"):
        parse_address(text)


def test_pointer_chains_are_parsed_from_profile_fields() -> None:
    chains = parse_pointer_chains([{"exe_sha256": "a" * 64, "address": "gta2.exe+272F40", "offsets": ["E4", "10"]}])

    assert chains == (PointerChain(exe_sha256="a" * 64, base=Address("gta2.exe", 0x272F40), offsets=(0xE4, 0x10)),)


def test_chain_is_chosen_by_executable_hash_ignoring_case() -> None:
    wanted = PointerChain(exe_sha256="a" * 64, base=Address("gta2.exe", 0x10), offsets=(0x4,))
    other = PointerChain(exe_sha256="b" * 64, base=Address("gta2.exe", 0x99), offsets=())

    assert chain_for((other, wanted), "A" * 64) is wanted


def test_unknown_game_build_is_rejected() -> None:
    with pytest.raises(UnsupportedAppVersion, match="not supported by its profile yet"):
        chain_for((), "c" * 64)


def test_resolve_follows_the_chain_from_a_module() -> None:
    # gta2.exe is loaded at 0x400000; the pointer at gta2.exe+10 points to 0x9000.
    memory = FakeMemory({0x400010: pointer(0x9000)}, {"gta2.exe": 0x400000})

    assert resolve(memory, Address("gta2.exe", 0x10), [0xE4]) == 0x90E4


def test_resolve_without_offsets_is_the_base_address() -> None:
    memory = FakeMemory({}, {"gta2.exe": 0x400000})

    assert resolve(memory, Address("GTA2.EXE", 0x10), []) == 0x400010


def test_null_pointer_means_no_text_yet() -> None:
    memory = FakeMemory({0x400010: pointer(0)}, {"gta2.exe": 0x400000})

    assert resolve(memory, Address("gta2.exe", 0x10), [0xE4]) is None


def test_missing_module_is_an_error() -> None:
    with pytest.raises(
        ProcessMemoryError, match="gta2.exe is not loaded in the app yet: if this lasts, the profile may not fit"
    ):
        resolve(FakeMemory({}, {}), Address("gta2.exe", 0x10), [0xE4])


def test_unreadable_pointer_is_an_error() -> None:
    with pytest.raises(MemoryReadError, match="profile may not fit this version") as raised:
        resolve(FakeMemory({}, {"gta2.exe": 0x400000}), Address("gta2.exe", 0x10), [0xE4])

    assert "400010" not in str(raised.value)
    assert "400010" in str(raised.value.__cause__)


def test_64_bit_pointers() -> None:
    memory = FakeMemory({0x1000: (0x1_2345_6780).to_bytes(8, "little")}, {}, pointer_size=8)

    assert resolve(memory, Address(None, 0x1000), [0x8]) == 0x1_2345_6788
