"""Quitting when the user signs out, and the named mutexes that tell the installer ReflektorTTS is running."""

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from typing import cast
from uuid import uuid4

import pytest

from reflektortts.desktop.system.session import announce_running, quit_on_sign_out


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
    assert mutex_exists(f"Global\\{name}")


def test_outside_windows_nothing_is_announced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert not announce_running(f"ReflektorTTS-test-{uuid4()}")


@pytest.mark.skipif(sys.platform != "win32", reason="The installer's mutex exists only on Windows")
def test_everyone_may_see_the_mutexes() -> None:
    if sys.platform != "win32":
        raise AssertionError("Windows only")
    name = f"ReflektorTTS-test-{uuid4()}"
    announce_running(name)
    kernel32 = ctypes.WinDLL("kernel32")
    advapi32 = ctypes.WinDLL("advapi32")
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    pointer = ctypes.c_void_p
    advapi32.GetSecurityInfo.argtypes = [
        pointer,
        ctypes.c_int,
        ctypes.c_uint32,
        pointer,
        pointer,
        pointer,
        pointer,
        pointer,
    ]
    kernel_object, dacl_only = 6, 4
    for full_name in (name, f"Global\\{name}"):
        handle = kernel32.OpenMutexW(0x00120000, False, full_name)  # SYNCHRONIZE | READ_CONTROL
        descriptor = ctypes.c_void_p()
        result = advapi32.GetSecurityInfo(
            handle, kernel_object, dacl_only, None, None, None, None, ctypes.byref(descriptor)
        )
        assert result == 0
        sddl = ctypes.c_wchar_p()
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4, ctypes.byref(sddl), None)
        assert "(A;;0x100000;;;WD)" in str(sddl.value)  # Everyone may wait on it.


class FakeRoot:
    """Records the window manager protocols handled, as Tk's root window would take them."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[], None]] = {}

    def protocol(self, name: str, handler: Callable[[], None]) -> None:
        self.handlers[name] = handler


def nothing() -> None:
    pass


@pytest.mark.parametrize(("platform", "handled"), [("win32", True), ("linux", False)])
def test_reflektortts_quits_when_the_user_signs_out_of_windows(
    monkeypatch: pytest.MonkeyPatch, platform: str, handled: bool
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    root = FakeRoot()

    quit_on_sign_out(cast(tk.Tk, root), nothing)

    assert root.handlers == ({"WM_SAVE_YOURSELF": nothing} if handled else {})
