"""The line at the bottom of the window: the open tab's own text, or, while the mouse is over a
button, what that button does."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class StatusBar:
    def __init__(self, parent: tk.Misc, row: int) -> None:
        """Takes two grid rows of parent, from row: a separator line, then the text."""
        ttk.Separator(parent, orient="horizontal").grid(row=row, column=0, sticky="ew")
        self._label = ttk.Label(parent, text="", anchor="w", padding=(8, 2, 8, 3))
        self._label.grid(row=row + 1, column=0, sticky="ew")
        self._texts: dict[str, str] = {}
        """Each tab's own text, by the tab's widget name."""
        self._page = ""
        self._hovering = False

    def set_text(self, page: tk.Misc, text: str) -> None:
        """Sets a tab's own text, shown while the tab is open and no button is hovered."""
        self._texts[str(page)] = text
        self._refresh()

    def show_page(self, page: str) -> None:
        """The tab with this widget name was opened."""
        self._page = page
        self._refresh()

    def hint(self, widget: tk.Misc, text: Callable[[], str]) -> None:
        """Shows text() while the mouse is over widget; it is asked then, so it can follow the
        widget's state (e.g. a button that downloads or removes)."""

        def enter(event: object) -> None:
            self._hovering = True
            self._label.configure(text=text())

        def leave(event: object) -> None:
            self._hovering = False
            self._refresh()

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")

    def _refresh(self) -> None:
        # A hint stays until the mouse leaves its button, even when the tab's text changes meanwhile.
        if not self._hovering:
            self._label.configure(text=self._texts.get(self._page, ""))
