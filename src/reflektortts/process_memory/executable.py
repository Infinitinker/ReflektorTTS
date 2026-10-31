"""The running game's executable: where it is, and which build of the game it is."""

import hashlib
from pathlib import Path

import psutil

from reflektortts.process_memory.memory import ProcessMemoryError


def executable_path(pid: int) -> Path:
    try:
        return Path(psutil.Process(pid).exe())
    except psutil.Error as error:
        raise ProcessMemoryError(f"Cannot find the game's files: {error}") from error


def executable_sha256(pid: int) -> str:
    """Identifies the build of the game."""
    path = executable_path(pid)
    try:
        with path.open("rb") as executable:
            return hashlib.file_digest(executable, "sha256").hexdigest()
    except OSError as error:
        raise ProcessMemoryError(f"Cannot identify the game's version: {error}") from error
