"""How the running desktop app makes itself known to the installer, so it can update or remove
ReflektorTTS: named mutexes, whose existence tells the installer ReflektorTTS is running, in this
user's session or, for an install for all users, in anyone's. Elsewhere than on Windows this does
nothing."""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

MUTEX_NAME = "ReflektorTTS"
"""Must match AppMutex in tools/installer.iss."""
SYNCHRONIZE = 0x00100000
EVERYONE_MAY_SEE_IT = "D:(A;;GA;;;SY)(A;;GA;;;OW)(A;;0x00100000;;;WD)"
"""The mutexes' access rules (SDDL): full access for the system and the user who created them, and
for everyone else only waiting on them, which is all the installer does. With the default rules
only their creator could open them, and an installer run by an administrator, or another user's
ReflektorTTS, would not see them."""
SDDL_REVISION_1 = 1


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", ctypes.c_uint32),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", ctypes.c_int),
    ]


def announce_running(name: str = MUTEX_NAME) -> bool:
    """Creates, or opens if another user's ReflektorTTS created it, the mutex in this session and its
    Global\\ twin, seen from every session, and never closes them: Windows removes them only when
    every process holding them has ended, so the installer waits until ReflektorTTS's files are free.
    Returns whether this process holds both."""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.CreateMutexExW.restype = ctypes.c_void_p
    kernel32.CreateMutexExW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        EVERYONE_MAY_SEE_IT, SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        logger.warning("Cannot describe who may see the %s mutex (error %d)", name, ctypes.get_last_error())
        return False
    attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
    held = True
    for full_name in (name, f"Global\\{name}"):
        # Asking only for SYNCHRONIZE also opens one another user created, which this process keeps alive.
        if not kernel32.CreateMutexExW(ctypes.byref(attributes), full_name, 0, SYNCHRONIZE):
            logger.warning("Cannot create the %s mutex (error %d)", full_name, ctypes.get_last_error())
            held = False
    kernel32.LocalFree(descriptor)
    return held
