"""How the running desktop app makes itself known to the installer, so it can update or remove
ReflektorTTS: a named mutex, whose existence tells the installer ReflektorTTS is running. Elsewhere
than on Windows this does nothing."""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

MUTEX_NAME = "ReflektorTTS"
"""Must match AppMutex in tools/installer.iss."""


def announce_running(name: str = MUTEX_NAME) -> bool:
    """Creates the mutex and never closes it: Windows removes it only when the process has ended,
    so the installer waits until ReflektorTTS's files are free. Returns whether it exists."""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logger.warning("Cannot create the %s mutex (error %d)", name, ctypes.get_last_error())
    return bool(handle)
