"""Helpers the window's tabs share for their tables and buttons."""

import tkinter.font as tkfont
from collections.abc import Sequence
from tkinter import ttk
from typing import Any

COLUMN_PADDING = 24
"""Pixels added to the widest text of a column."""
FLAT_TREEVIEW = "Flat.Treeview"
"""A table's style whose rows never expand (see flat_treeview_style)."""


def button_width(labels: Sequence[str]) -> int:
    """A button's width for its longest label, so it never changes and the buttons after it never
    move; in average character widths, so a little room is left for wider letters."""
    return max(len(label) for label in labels) + 2


def _without_indicator(layout: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """A ttk layout without its tree indicator element, at any depth."""
    kept = []
    for element, options in layout:
        if element.endswith(".indicator"):
            continue
        if "children" in options:
            options = options | {"children": _without_indicator(options["children"])}
        kept.append((element, options))
    return kept


def flat_treeview_style() -> str:
    """The style of a table whose rows never expand: like the theme's, but its first column (#0)
    leaves no room for the arrow that would expand a row, so a row's image starts at the column's
    left edge. Tkinter must be running."""
    style = ttk.Style()
    style.layout(f"{FLAT_TREEVIEW}.Item", _without_indicator(style.layout("Treeview.Item")))
    return FLAT_TREEVIEW


def _fonts() -> tuple[tkfont.Font, tkfont.Font]:
    """A table's font, and its titles'."""
    style = ttk.Style()
    font = tkfont.nametofont(style.lookup("Treeview", "font") or "TkDefaultFont")
    heading = tkfont.nametofont(style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    return font, heading


def fit_columns(tree: ttk.Treeview, columns: Sequence[tuple[str, str]]) -> None:
    """Sizes each column to its widest text, title included; a column set to stretch also takes
    the room left."""
    font, heading = _fonts()
    rows = tree.get_children()
    for column, title in columns:
        texts = [str(tree.set(row, column)) for row in rows]
        width = max([heading.measure(title), *(font.measure(text) for text in texts)])
        tree.column(column, width=width + COLUMN_PADDING)


def fit_tree_column(tree: ttk.Treeview, title: str, image_width: int) -> None:
    """Sizes the first column (#0, each row's text and image) to its widest text and the image,
    title included."""
    font, heading = _fonts()
    texts = [str(tree.item(row, "text")) for row in tree.get_children()]
    width = max([heading.measure(title), *(font.measure(text) + image_width for text in texts)])
    tree.column("#0", width=width + COLUMN_PADDING)


def row_image_size() -> int:
    """The size of an image that fits a table's row, in pixels: the height of its text."""
    return int(_fonts()[0].metrics("linespace"))
