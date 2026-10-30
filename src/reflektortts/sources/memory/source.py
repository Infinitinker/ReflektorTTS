"""MemorySource: reads the game's current text through a pointer chain."""

import re
from dataclasses import dataclass

from reflektortts.sources.memory.pointer import Address, resolve
from reflektortts.sources.memory.process_memory import MemoryReadError, ProcessMemory

MAX_CHARS = 400

_CONTROL = re.compile("[\x00-\x1f�]+")


class UnsupportedGameVersion(Exception):
    """The profile has no pointer for this build of the game."""


@dataclass(frozen=True)
class PointerChain:
    exe_sha256: str
    """SHA-256 of the game executable the chain was found in."""
    base: Address
    offsets: tuple[int, ...]


@dataclass(frozen=True)
class MemorySettings:
    encoding: str
    pointers: tuple[PointerChain, ...]


def decode_text(raw: bytes, encoding: str) -> str:
    """Decodes a zero-terminated string; control characters become spaces."""
    if encoding.startswith("utf-16"):
        end = next((i for i in range(0, len(raw) - 1, 2) if raw[i : i + 2] == b"\0\0"), len(raw) - len(raw) % 2)
    else:
        end = raw.find(b"\0") if b"\0" in raw else len(raw)
    return _CONTROL.sub(" ", raw[:end].decode(encoding, errors="replace")).strip()


class MemorySource:
    def __init__(
        self,
        name: str,
        poll_interval: float,
        settings: MemorySettings,
        memory: ProcessMemory,
        exe_sha256: str,
    ) -> None:
        chain = next((p for p in settings.pointers if p.exe_sha256.lower() == exe_sha256.lower()), None)
        if chain is None:
            memory.close()
            raise UnsupportedGameVersion(
                "This version of the game is not supported by its profile yet "
                f"(game executable SHA-256 {exe_sha256}). Check for an updated profile."
            )
        self.name = name
        self.poll_interval = poll_interval
        self._encoding = settings.encoding
        self._chain = chain
        self._memory = memory

    def read(self) -> str | None:
        address = resolve(self._memory, self._chain.base, self._chain.offsets)
        if address is None:
            return None
        width = 2 if self._encoding.startswith("utf-16") else 1
        raw = self._memory.read(address, MAX_CHARS * width)
        if not raw:
            raise MemoryReadError(f"Cannot read the game's text at {address:X}.")
        return decode_text(raw, self._encoding) or None

    def close(self) -> None:
        self._memory.close()
