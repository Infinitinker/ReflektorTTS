"""The ReflektorTTS window's colors and fonts, shared by its tabs.

Fonts are derived from Tk's named fonts, so they follow the system's (Segoe UI on Windows).
"""

import tkinter as tk
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


def title_font() -> tkfont.Font:
    """The default font, bold and much larger, for the app's name; needs the Tk root to exist."""
    font = tkfont.nametofont("TkDefaultFont").copy()
    size = int(font.actual("size"))
    font.configure(weight="bold", size=size + 8 if size > 0 else size - 11)
    return font


def group_background() -> str:
    """The background inside a group box (ttk.LabelFrame), for widgets that should blend into it."""
    return str(ttk.Style().lookup("TLabelframe", "background"))


def draws_without_xft(root: tk.Misc) -> bool:
    """Whether Tk draws with X11's core fonts instead of Xft, as the Tk in uv's Python does: it then
    shows text beyond Latin-1, such as "ł" or "…", as wrong symbols."""
    try:
        return bool(
            root.tk.call("tk", "windowingsystem") == "x11"
            and root.tk.call("::tk::pkgconfig", "get", "fontsystem") != "xft"
        )
    except tk.TclError:
        # A Tk too old to tell; distributions build theirs with Xft.
        return False
