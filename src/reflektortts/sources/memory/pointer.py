"""Pointer chains in Cheat Engine notation: a base address like "gta2.exe+272F40", then offsets."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from reflektortts.sources.memory.process_memory import MemoryReadError, ProcessMemory, ProcessMemoryError

_ADDRESS = re.compile(r"^(?:(?P<module>[^+]+)\+)?(?P<offset>[0-9A-Fa-f]+)$")


@dataclass(frozen=True)
class Address:
    module: str | None
    """Module the offset is relative to, or None for an absolute address."""
    offset: int


def parse_address(text: str) -> Address:
    match = _ADDRESS.match(text.strip())
    if match is None:
        raise ValueError(f'"{text}" is not an address like "game.exe+1A2B" or "1A2B"')
    return Address(module=match["module"], offset=int(match["offset"], 16))


def resolve(memory: ProcessMemory, base: Address, offsets: Sequence[int]) -> int | None:
    """Follows the chain: read the pointer at the current address, add the next offset.

    Returns None if a pointer on the way is null, which games use for "nothing there yet".
    """
    address = base.offset
    if base.module is not None:
        module_base = memory.module_base(base.module)
        if module_base is None:
            raise ProcessMemoryError(f"{base.module} is not loaded in the game.")
        address += module_base
    for offset in offsets:
        raw = memory.read(address, memory.pointer_size)
        if len(raw) < memory.pointer_size:
            raise MemoryReadError(f"Cannot read the game's memory at {address:X}.")
        pointer = int.from_bytes(raw, "little")
        if pointer == 0:
            return None
        address = pointer + offset
    return address
