"""MemorySource: reads the app's current text through a pointer chain."""

import re
from dataclasses import dataclass

from reflektortts.languages import Languages
from reflektortts.process_memory.memory import MemoryReadError, ProcessMemory
from reflektortts.process_memory.pointer import PointerChain, resolve

MAX_CHARS = 400

_CONTROL = re.compile("[\x00-\x1f�]+")

# A pointer can outlive its text, e.g. in the app's menu, and then points at unrelated
# memory. Below this share of characters that can appear in dialogue, what was read is
# not text (a threshold proven on GTA2).
MIN_TEXT_RATIO = 0.9


@dataclass(frozen=True)
class MemorySettings:
    encoding: str
    pointers: tuple[PointerChain, ...]


def decode_terminated(raw: bytes, encoding: str) -> str:
    """Decodes a zero-terminated string as it is, control characters included."""
    if encoding.startswith("utf-16"):
        end = next((i for i in range(0, len(raw) - 1, 2) if raw[i : i + 2] == b"\0\0"), len(raw) - len(raw) % 2)
    else:
        end = raw.find(b"\0") if b"\0" in raw else len(raw)
    return raw[:end].decode(encoding, errors="replace")


def clean(text: str) -> str:
    """Turns control characters into spaces and trims the ends."""
    return _CONTROL.sub(" ", text).strip()


def can_appear_in_dialogue(character: str) -> bool:
    """Latin letters (with Polish and other accents), Cyrillic, spaces and common punctuation."""
    code = ord(character)
    return 0x20 <= code < 0x250 or 0x400 <= code < 0x500 or 0x2010 <= code < 0x2070


def looks_like_text(text: str) -> bool:
    return bool(text) and sum(map(can_appear_in_dialogue, text)) / len(text) >= MIN_TEXT_RATIO


class MemorySource:
    def __init__(
        self, name: str, poll_interval: float, encoding: str, chain: PointerChain, memory: ProcessMemory
    ) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._encoding = encoding
        self._chain = chain
        self._memory = memory

    def read(self, languages: Languages) -> str | None:
        address = resolve(self._memory, self._chain.base, self._chain.offsets)
        if address is None:
            return None
        width = 2 if self._encoding.startswith("utf-16") else 1
        raw = self._memory.read(address, MAX_CHARS * width)
        if not raw:
            raise MemoryReadError(
                "The text could not be read from the app: if this lasts, the profile may not fit this version of it."
            ) from MemoryReadError(f"Nothing could be read at {address:X}")
        # Checked before cleaning, which would turn control-character garbage into spaces.
        text = decode_terminated(raw, self._encoding)
        if not looks_like_text(text):
            return None
        return clean(text) or None

    def close(self) -> None:
        self._memory.close()
