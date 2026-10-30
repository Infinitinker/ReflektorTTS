"""Per-app volume on Windows: a process's audio sessions, the sliders of the volume mixer (WASAPI)."""

import threading
from typing import Any

import comtypes
from pycaw.pycaw import AudioUtilities

_thread = threading.local()


def _init_com() -> None:
    """COM needs initializing once on each thread that uses it."""
    if not getattr(_thread, "com_ready", False):
        comtypes.CoInitialize()
        _thread.com_ready = True


class SessionsVolume:
    """All audio sessions of one process, set together; use it on the thread that opened it."""

    def __init__(self, volumes: list[Any]) -> None:
        self._volumes = volumes

    def get(self) -> float:
        return float(self._volumes[0].GetMasterVolume())

    def set(self, level: float) -> None:
        for volume in self._volumes:
            volume.SetMasterVolume(level, None)


def open_app_volume(pid: int) -> SessionsVolume | None:
    _init_com()
    volumes = [session.SimpleAudioVolume for session in AudioUtilities.GetAllSessions() if session.ProcessId == pid]
    return SessionsVolume(volumes) if volumes else None
