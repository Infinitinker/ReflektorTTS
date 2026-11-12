"""Reading another process's memory, with one implementation per OS."""

import sys
from typing import Protocol


class ProcessMemoryError(Exception):
    """The app's memory cannot be accessed; the message says what to do."""


class MemoryReadError(ProcessMemoryError):
    """An address in the app's memory cannot be read."""


class ProcessMemory(Protocol):
    pointer_size: int
    """Size of a pointer in the app: 4 for 32-bit apps, 8 for 64-bit ones."""

    def read(self, address: int, size: int) -> bytes:
        """Returns up to size bytes from address; fewer where readable memory ends, none if unreadable."""

    def module_base(self, name: str) -> int | None:
        """Returns where a loaded module (e.g. "gta2.exe") starts, or None if it is not loaded."""

    def close(self) -> None: ...


def open_process_memory(pid: int) -> ProcessMemory:
    if sys.platform == "win32":
        from reflektortts.process_memory.windows import WindowsProcessMemory

        return WindowsProcessMemory(pid)
    raise ProcessMemoryError("Reading an app’s memory is supported only on Windows so far.")
