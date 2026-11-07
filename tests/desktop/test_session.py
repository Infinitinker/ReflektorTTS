import ctypes
import sys
from uuid import uuid4

import pytest

from reflektortts.desktop.session import announce_running


def mutex_exists(name: str) -> bool:
    if sys.platform != "win32":
        raise AssertionError("Mutexes are a Windows thing")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(0x00100000, False, name)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
    return bool(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="The installer's mutex exists only on Windows")
def test_the_installer_can_see_reflektortts_running() -> None:
    # A name of its own, so a ReflektorTTS running on this computer does not matter.
    name = f"ReflektorTTS-test-{uuid4()}"
    assert not mutex_exists(name)

    assert announce_running(name)

    assert mutex_exists(name)


def test_outside_windows_nothing_is_announced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert not announce_running(f"ReflektorTTS-test-{uuid4()}")
