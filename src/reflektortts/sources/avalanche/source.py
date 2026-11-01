"""AvalancheSource: reads the subtitle shown in a game on Avalanche Studios' engine."""

import logging

from reflektortts.languages import Languages
from reflektortts.process_memory.memory import MemoryReadError, ProcessMemory
from reflektortts.process_memory.pointer import PointerChain, resolve
from reflektortts.sources.avalanche.line_texts import LineTexts

logger = logging.getLogger(__name__)

NO_LINE = 0


class AvalancheSource:
    """The game's subtitle element holds the ID of the line it shows, the same in every language,
    or 0 when no subtitle is shown. Its text, in the input language, comes from the game's files.
    """

    def __init__(
        self, name: str, poll_interval: float, chain: PointerChain, memory: ProcessMemory, texts: LineTexts
    ) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._chain = chain
        self._memory = memory
        self._texts = texts
        self._unknown: set[int] = set()

    def read(self, languages: Languages) -> str | None:
        # Asked for on every read, so the text is read as soon as the game starts, before its
        # first subtitle.
        lines = self._texts.lines(languages.input)
        line_id = self._shown_line()
        if line_id == NO_LINE or lines is None:
            return None
        text = lines.get(line_id)
        if text is None and line_id not in self._unknown:
            self._unknown.add(line_id)
            logger.info("%s: line %08X is not in the game's text", self.name, line_id)
        return text

    def close(self) -> None:
        self._texts.close()
        self._memory.close()

    def _shown_line(self) -> int:
        address = resolve(self._memory, self._chain.base, self._chain.offsets)
        if address is None:
            return NO_LINE
        raw = self._memory.read(address, 4)
        if len(raw) < 4:
            raise MemoryReadError(f"Cannot read the shown line's ID at {address:X}.")
        return int.from_bytes(raw, "little")
