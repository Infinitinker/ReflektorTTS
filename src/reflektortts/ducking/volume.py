"""The volume of one application's sound, as in the system's volume mixer; one implementation per OS."""

import sys
from collections.abc import Callable
from typing import Protocol


class AppVolume(Protocol):
    """A process's volume, from 0.0 to 1.0. Calls may raise if the process has stopped playing."""

    def get(self) -> float: ...

    def set(self, level: float) -> None: ...


type OpenAppVolume = Callable[[int], AppVolume | None]
"""Finds a process's sound by PID; None while it plays none."""


class DuckingUnavailableError(Exception):
    """This operating system has no implementation yet."""


def system_app_volume() -> OpenAppVolume:
    if sys.platform == "win32":
        from reflektortts.ducking.windows import open_app_volume

        return open_app_volume
    raise DuckingUnavailableError("Lowering an app’s sound is not available on this system yet.")
