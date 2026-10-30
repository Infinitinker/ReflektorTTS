import pytest

from reflektortts.sources.memory.fake_memory import FakeMemory
from reflektortts.sources.memory.pointer import Address, parse_address, resolve
from reflektortts.sources.memory.process_memory import MemoryReadError, ProcessMemoryError


def pointer(value: int) -> bytes:
    return value.to_bytes(4, "little")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("gta2.exe+272F40", Address("gta2.exe", 0x272F40)),
        ("4A2F40", Address(None, 0x4A2F40)),
        (" game.exe+ff ", Address("game.exe", 0xFF)),
    ],
)
def test_parse_address(text: str, expected: Address) -> None:
    assert parse_address(text) == expected


@pytest.mark.parametrize("text", ["", "gta2.exe+", "+12", "gta2.exe+XYZ"])
def test_parse_address_rejects_bad_text(text: str) -> None:
    with pytest.raises(ValueError, match="is not an address"):
        parse_address(text)


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
    with pytest.raises(ProcessMemoryError, match="gta2.exe is not loaded"):
        resolve(FakeMemory({}, {}), Address("gta2.exe", 0x10), [0xE4])


def test_unreadable_pointer_is_an_error() -> None:
    with pytest.raises(MemoryReadError, match="400010"):
        resolve(FakeMemory({}, {"gta2.exe": 0x400000}), Address("gta2.exe", 0x10), [0xE4])


def test_64_bit_pointers() -> None:
    memory = FakeMemory({0x1000: (0x1_2345_6780).to_bytes(8, "little")}, {}, pointer_size=8)

    assert resolve(memory, Address(None, 0x1000), [0x8]) == 0x1_2345_6788
