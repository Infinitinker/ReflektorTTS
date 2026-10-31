"""Which build of a game is running, by the SHA-256 of its executable."""

import hashlib

import psutil

from reflektortts.process_memory.memory import ProcessMemoryError


def executable_sha256(pid: int) -> str:
    try:
        path = psutil.Process(pid).exe()
        with open(path, "rb") as executable:
            return hashlib.file_digest(executable, "sha256").hexdigest()
    except (psutil.Error, OSError) as error:
        raise ProcessMemoryError(f"Cannot identify the game's version: {error}") from error
