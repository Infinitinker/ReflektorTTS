"""AvalancheSource: reads the subtitle shown in a game on Avalanche Studios' engine."""

import logging

from reflektortts.process_memory.memory import MemoryReadError, ProcessMemory
from reflektortts.process_memory.pointer import PointerChain, resolve

logger = logging.getLogger(__name__)

NO_LINE = 0


class AvalancheSource:
    """The game's subtitle element holds the ID of the line it shows, the same in every language,
    or 0 when no subtitle is shown. The source logs each line's ID; it does not read the line's
    text yet, so it reads as no text."""

    def __init__(self, name: str, poll_interval: float, chain: PointerChain, memory: ProcessMemory) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._chain = chain
        self._memory = memory
        self._shown = NO_LINE

    def read(self) -> str | None:
        line_id = self._shown_line()
        if line_id != self._shown and line_id != NO_LINE:
            logger.info("%s: line %08X shown", self.name, line_id)
        self._shown = line_id
        return None

    def close(self) -> None:
        self._memory.close()

    def _shown_line(self) -> int:
        address = resolve(self._memory, self._chain.base, self._chain.offsets)
        if address is None:
            return NO_LINE
        raw = self._memory.read(address, 4)
        if len(raw) < 4:
            raise MemoryReadError(f"Cannot read the shown line's ID at {address:X}.")
        return int.from_bytes(raw, "little")
