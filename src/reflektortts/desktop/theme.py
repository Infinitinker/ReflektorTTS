"""The desktop window's colors and fonts, shared by its tabs.

Fonts are derived from Tk's named fonts, so they follow the system's (Segoe UI on Windows).
"""

import tkinter.font as tkfont
from tkinter import ttk

GOOD = "#0a7a0a"
"""Text for what works: an installed entry, an app being read."""
BUSY = "#9a6b00"
"""Text for what is under way or on hold: a download, paused reading."""
DIM = "#666666"
"""Secondary text."""


def heading_font() -> tkfont.Font:
    """The default font, bold and a little larger; needs the Tk root to exist."""
    font = tkfont.nametofont("TkDefaultFont").copy()
    size = int(font.actual("size"))
    # Positive sizes are points, negative ones pixels.
    font.configure(weight="bold", size=size + 2 if size > 0 else size - 3)
    return font


def group_background() -> str:
    """The background inside a group box (ttk.LabelFrame), for widgets that should blend into it."""
    return str(ttk.Style().lookup("TLabelframe", "background"))
