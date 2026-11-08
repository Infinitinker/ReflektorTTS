"""A window's place on the screen, in physical pixels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class Screen:
    """Where a window is, and the display it is on."""

    frame: Rect
    """The window's visible frame, title bar included."""
    work_area: Rect
    """The part of its display that windows may use: without the taskbar."""
    scale: float
    """The display's scale: 1.0 at 100%, 1.5 at 150%."""
