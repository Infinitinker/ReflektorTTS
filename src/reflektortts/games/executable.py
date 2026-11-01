"""A running program's executable: where it is, and which build it is."""

import hashlib
from pathlib import Path

import psutil


class ExecutableError(Exception):
    """A program's executable cannot be found or read; the message says why."""


def executable_path(pid: int) -> Path:
    try:
        return Path(psutil.Process(pid).exe())
    except psutil.Error as error:
        raise ExecutableError(f"Cannot find the program's files: {error}") from error


def executable_sha256(pid: int) -> str:
    """Identifies the build, by the SHA-256 of the executable in lowercase hex."""
    path = executable_path(pid)
    try:
        with path.open("rb") as executable:
            return hashlib.file_digest(executable, "sha256").hexdigest()
    except OSError as error:
        raise ExecutableError(f"Cannot identify the program's version: {error}") from error
