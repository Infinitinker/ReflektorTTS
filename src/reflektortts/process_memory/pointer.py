"""Pointer chains in Cheat Engine notation: a base address like "gta2.exe+272F40", then offsets."""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from reflektortts.process_memory.memory import MemoryReadError, ProcessMemory, ProcessMemoryError

_ADDRESS = re.compile(r"^(?:(?P<module>[^+]+)\+)?(?P<offset>[0-9A-Fa-f]+)$")


class UnsupportedGameVersion(Exception):
    """The profile has no pointer for this build of the game."""


@dataclass(frozen=True)
class Address:
    module: str | None
    """Module the offset is relative to, or None for an absolute address."""
    offset: int


@dataclass(frozen=True)
class PointerChain:
    exe_sha256: str
    """SHA-256 of the game executable the chain was found in."""
    base: Address
    offsets: tuple[int, ...]


def parse_address(text: str) -> Address:
    match = _ADDRESS.match(text.strip())
    if match is None:
        raise ValueError(f'"{text}" is not an address like "game.exe+1A2B" or "1A2B"')
    return Address(module=match["module"], offset=int(match["offset"], 16))


def parse_pointer_chains(entries: Iterable[Mapping[str, Any]]) -> tuple[PointerChain, ...]:
    """Turns a profile's schema-validated "pointers" entries into chains."""
    return tuple(
        PointerChain(
            exe_sha256=entry["exe_sha256"],
            base=parse_address(entry["address"]),
            offsets=tuple(int(offset, 16) for offset in entry["offsets"]),
        )
        for entry in entries
    )


def chain_for(chains: Iterable[PointerChain], exe_sha256: str) -> PointerChain:
    """The chain found in this build of the game."""
    chain = next((chain for chain in chains if chain.exe_sha256.lower() == exe_sha256.lower()), None)
    if chain is None:
        raise UnsupportedGameVersion(
            "This version of the game is not supported by its profile yet "
            f"(game executable SHA-256 {exe_sha256}). Check for an updated profile."
        )
    return chain


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
