"""Where the settings window opens: beside the desktop app's window, like a sidebar, and as tall.

Everything here is in physical pixels of the screen, which the settings window takes on its command
line (see native/README.md). Tk's own measures cannot be used for that on Windows: Python and
reflektortts.exe are not DPI aware, so at a display scale above 100% Windows scales the window up
and gives Tk smaller, scaled-down measures. There the window's place comes from Windows instead
(win32_windows.py), and where Windows cannot tell, the settings window opens centered instead;
elsewhere Tk's measures are physical pixels.

Edges are as Windows' rectangles have them: a left or top edge is the first pixel inside, a right or
bottom edge the first one past it."""

import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Literal

from reflektortts.desktop.panel import win32_windows
from reflektortts.desktop.panel.screen import Rect, Screen

PANEL_WIDTH = 436
"""The settings window's width at 100% display scale, its frame included: the overlay panel's width,
kSettingsPanelWidth in native/shared/settings_panel.h (420), ImGui's scrollbar (14), and a pixel of
border on each side. Only used to choose the side it fits on: change it with kSettingsPanelWidth."""

Side = Literal["right", "left"]


@dataclass(frozen=True)
class Dock:
    """Where the settings window opens, as its --dock-* arguments say."""

    side: Side
    x: int
    """The edge the two windows share: on the right, the desktop window's right edge, which is the
    settings window's left edge, its first pixel; on the left, the desktop window's left edge, which
    is the settings window's right edge, the first pixel past it. Either way the settings window's
    pixel next to the edge (x on the right, x - 1 on the left) is on the desktop window's display."""
    y: int
    """The top of both windows."""
    height: int
    """Both windows' height, frame and title bar included."""

    def arguments(self) -> list[str]:
        return [
            "--dock-side",
            self.side,
            "--dock-x",
            str(self.x),
            "--dock-y",
            str(self.y),
            "--dock-height",
            str(self.height),
        ]


def dock_beside(screen: Screen) -> Dock:
    """On the right of the desktop window if the settings window fits there on its display, else on
    its left; if it fits on neither side, over the desktop window, at the display's right edge."""
    frame, work_area = screen.frame, screen.work_area
    width = round(PANEL_WIDTH * screen.scale)
    if frame.right + width <= work_area.right:
        return Dock("right", frame.right, frame.top, frame.height)
    if frame.left - width >= work_area.left:
        return Dock("left", frame.left, frame.top, frame.height)
    return Dock("left", work_area.right, frame.top, frame.height)


def dock_of(root: tk.Misc) -> Dock | None:
    """Where the settings window opens beside the desktop window; None, to open it centered, where
    the desktop window's place cannot be told."""
    screen = screen_of(root)
    return dock_beside(screen) if screen is not None else None


def tk_screen(root: tk.Misc) -> Screen:
    """The window and its screen as Tk measures them: the inside of the window only, since Tk does
    not know its frame, and the whole screen."""
    left, top = root.winfo_rootx(), root.winfo_rooty()
    return Screen(
        frame=Rect(left, top, left + root.winfo_width(), top + root.winfo_height()),
        work_area=Rect(0, 0, root.winfo_screenwidth(), root.winfo_screenheight()),
        scale=root.winfo_fpixels("1i") / 96,
    )


def screen_of(root: tk.Misc) -> Screen | None:
    """Where the desktop window is, and the work area and scale of the display it is on; None on
    Windows where Windows cannot tell, since Tk's measures are not physical pixels there."""
    if sys.platform == "win32":
        return win32_windows.window_screen(root.winfo_id())
    return tk_screen(root)
