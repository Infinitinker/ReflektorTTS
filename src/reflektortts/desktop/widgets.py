"""Helpers the window's tabs share for their tables and buttons."""

import tkinter.font as tkfont
from collections.abc import Sequence
from tkinter import ttk

COLUMN_PADDING = 24
"""Pixels added to the widest text of a column."""


def button_width(labels: Sequence[str]) -> int:
    """A button's width for its longest label, so it never changes and the buttons after it never
    move; in average character widths, so a little room is left for wider letters."""
    return max(len(label) for label in labels) + 2


def fit_columns(tree: ttk.Treeview, columns: Sequence[tuple[str, str]]) -> None:
    """Sizes each column to its widest text, title included; a column set to stretch also takes
    the room left."""
    style = ttk.Style()
    font = tkfont.nametofont(style.lookup("Treeview", "font") or "TkDefaultFont")
    heading = tkfont.nametofont(style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    rows = tree.get_children()
    for column, title in columns:
        texts = [str(tree.set(row, column)) for row in rows]
        width = max([heading.measure(title), *(font.measure(text) for text in texts)])
        tree.column(column, width=width + COLUMN_PADDING)
