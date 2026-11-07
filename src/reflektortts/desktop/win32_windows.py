"""What the desktop app asks Windows about windows: where its own window is, in physical pixels, and
bringing another program's window to the front. Elsewhere than on Windows these do nothing."""

import ctypes
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

from reflektortts.desktop.screen import Rect, Screen

logger = logging.getLogger(__name__)

GA_ROOT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
MONITOR_DEFAULTTONEAREST = 2
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
MDT_EFFECTIVE_DPI = 0
USER_DEFAULT_SCREEN_DPI = 96
GW_OWNER = 4
SW_RESTORE = 9


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _rect(rect: wintypes.RECT) -> Rect:
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def window_screen(widget: int) -> Screen | None:
    """Where the top-level window holding the widget (a Tk window's winfo_id()) is, and its
    display's work area and scale, all in physical pixels whatever the process's DPI awareness.
    None, after logging why, where Windows cannot tell."""
    if sys.platform != "win32":
        return None
    try:
        return _measure(widget)
    except (AttributeError, OSError) as error:
        # AttributeError: a function missing from this Windows, as SetThreadDpiAwarenessContext is
        # before Windows 10 version 1607.
        logger.warning("Cannot tell where the window is: %s", error)
        return None


def _measure(widget: int) -> Screen | None:
    """window_screen, raising AttributeError or OSError where Windows lacks or fails a function."""
    if sys.platform != "win32":
        raise OSError("Only Windows can tell")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi")
    shcore = ctypes.WinDLL("shcore")
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    shcore.GetDpiForMonitor.restype = ctypes.c_long
    shcore.GetDpiForMonitor.argtypes = [
        wintypes.HMONITOR,
        ctypes.c_int,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
    ]

    @contextmanager
    def thread_dpi_awareness(context: int) -> Iterator[None]:
        # The thread's DPI awareness decides whether Windows answers in physical pixels and with the
        # display's own DPI, or in the scaled-down pixels and the 96 DPI a DPI-unaware program sees;
        # it is put back right after.
        previous = user32.SetThreadDpiAwarenessContext(context)
        if previous is None:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            user32.SetThreadDpiAwarenessContext(previous)

    def monitor_info(monitor: int) -> _MonitorInfo:
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info

    window = user32.GetAncestor(widget, GA_ROOT)
    frame = wintypes.RECT()
    # The visible frame, without the invisible borders for resizing; never scaled for DPI.
    result = dwmapi.DwmGetWindowAttribute(
        window, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame), ctypes.sizeof(frame)
    )
    if not window or result != 0:
        logger.warning("Cannot tell where the window is (error %#x)", result & 0xFFFFFFFF)
        return None
    monitor = user32.MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST)
    dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
    with thread_dpi_awareness(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
        physical = monitor_info(monitor)
        result = shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    if result == 0 and dpi_x.value > 0:
        scale = dpi_x.value / USER_DEFAULT_SCREEN_DPI
    else:
        logger.info("Cannot tell the display's DPI (error %#x): comparing its sizes", result & 0xFFFFFFFF)
        # A DPI-unaware program sees the display shrunk by its scale.
        with thread_dpi_awareness(DPI_AWARENESS_CONTEXT_UNAWARE):
            scaled = monitor_info(monitor)
        scaled_width = scaled.rcMonitor.right - scaled.rcMonitor.left
        physical_width = physical.rcMonitor.right - physical.rcMonitor.left
        scale = physical_width / scaled_width if scaled_width > 0 else 1.0
    return Screen(frame=_rect(frame), work_area=_rect(physical.rcWork), scale=scale)


def bring_to_front(pid: int) -> bool:
    """Brings the process's main window to the front, restoring it if minimized. Windows lets only
    the program in front do that to another's window, as the desktop app is when the user has just
    clicked in it. Returns whether the window came to the front."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    for name in ("IsWindowVisible", "IsIconic", "SetForegroundWindow"):
        getattr(user32, name).argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    found: list[int] = []

    def visit(window: int, _: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        # Its top-level, unowned window: not a tooltip or a hidden helper window.
        if owner.value == pid and user32.IsWindowVisible(window) and not user32.GetWindow(window, GW_OWNER):
            found.append(window)
            return False
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    if not found:
        return False
    if user32.IsIconic(found[0]):
        user32.ShowWindow(found[0], SW_RESTORE)
    return bool(user32.SetForegroundWindow(found[0]))
