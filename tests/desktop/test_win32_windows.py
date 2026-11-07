import ctypes
import logging
import subprocess
import sys
import tkinter as tk

import pytest

from reflektortts.desktop.win32_windows import bring_to_front, window_screen


def test_a_process_without_a_window_is_not_brought_to_the_front() -> None:
    # A console program started without a console has no window of its own.
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert not bring_to_front(process.pid)
    finally:
        process.kill()
        process.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows can tell")
def test_elsewhere_windows_is_not_asked() -> None:
    assert window_screen(0) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_a_window_is_measured_in_physical_pixels_on_its_display() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display")
    try:
        root.geometry("400x300+100+100")
        root.withdraw()
        root.update_idletasks()

        screen = window_screen(root.winfo_id())

        assert screen is not None
        assert screen.scale >= 1.0
        # The frame: the inside, scaled to physical pixels, and a border, but not the invisible ones.
        assert 400 * screen.scale <= screen.frame.width <= 400 * screen.scale + 4
        assert screen.work_area.width > 0 and screen.work_area.height > 0
    finally:
        root.destroy()


class OldWindows:
    """A DLL of a Windows without the functions asked for."""

    def __init__(self, name: str, use_last_error: bool = False) -> None:
        self.name = name

    def __getattr__(self, function: str) -> object:
        raise AttributeError(f"function '{function}' not found")


def missing_dll(name: str, use_last_error: bool = False) -> object:
    raise OSError(f"Could not find module '{name}'")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
@pytest.mark.parametrize("dll", [OldWindows, missing_dll])
def test_where_windows_lacks_what_is_asked_it_cannot_tell(
    dll: object, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(ctypes, "WinDLL", dll)

    with caplog.at_level(logging.WARNING):
        assert window_screen(42) is None

    assert "Cannot tell where the window is" in caplog.text
