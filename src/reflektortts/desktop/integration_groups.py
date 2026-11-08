"""The Profiles tab's integration groups: for the selected profile, one group per integration its
sources need, titled with the integration's name, with what it does, its state and a button that
enables or disables it."""

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from reflektortts.desktop.integrations import ACTION_LABELS, IntegrationItem, action, action_hint, state_text
from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import BUSY, GOOD
from reflektortts.desktop.widgets import button_width

STATE_COLORS = {"enabled": GOOD, "unavailable": BUSY}
"""Text color of the state: green when enabled, amber when it cannot be; otherwise the default."""
PADDING = 8


class IntegrationGroups:
    def __init__(
        self, parent: tk.Misc, status_bar: StatusBar, on_change: Callable[[IntegrationItem, bool], None]
    ) -> None:
        """on_change is given an integration and whether to enable it."""
        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(0, weight=1)
        self._status_bar = status_bar
        self._on_change = on_change
        self._groups: list[_Group] = []

    def show(self, items: Sequence[IntegrationItem]) -> None:
        """Shows these integrations. The groups are made again only for other integrations, so a
        button under the mouse stays, with its hint, while its state changes."""
        if [group.item.id for group in self._groups] != [item.id for item in items]:
            for group in self._groups:
                group.frame.destroy()
            self._groups = [
                _Group(self.frame, row, item, self._status_bar, self._on_change) for row, item in enumerate(items)
            ]
        for group, item in zip(self._groups, items, strict=True):
            group.show(item)


class _Group:
    def __init__(
        self,
        parent: ttk.Frame,
        row: int,
        item: IntegrationItem,
        status_bar: StatusBar,
        on_change: Callable[[IntegrationItem, bool], None],
    ) -> None:
        self.item = item
        self._on_change = on_change
        self.frame = ttk.LabelFrame(parent, text=item.name, padding=(PADDING, 2, PADDING, 6))
        self.frame.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        self.frame.columnconfigure(1, weight=1)
        self._description = ttk.Label(self.frame, text="", justify="left")
        self._description.grid(row=0, column=0, columnspan=2, sticky="w")
        self._button = ttk.Button(
            self.frame, text=ACTION_LABELS[0], width=button_width(ACTION_LABELS), command=self._act
        )
        self._button.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._state = ttk.Label(self.frame, text="", justify="left")
        self._state.grid(row=1, column=1, sticky="w", padx=(PADDING, 0), pady=(6, 0))
        status_bar.hint(self._button, lambda: action_hint(self.item))
        self.frame.bind("<Configure>", self._wrap)

    def show(self, item: IntegrationItem) -> None:
        self.item = item
        self._description.configure(text=item.description)
        self._state.configure(text=state_text(item), foreground=STATE_COLORS.get(item.state, ""))
        label, clickable = action(item)
        self._button.configure(text=label, state="normal" if clickable else "disabled")

    def _wrap(self, event: "tk.Event[tk.Misc]") -> None:
        """Long texts wrap within the group, as wide as the window makes it."""
        width = event.width - 2 * PADDING - 4
        self._description.configure(wraplength=max(width, 1))
        self._state.configure(wraplength=max(width - self._button.winfo_width() - PADDING, 1))

    def _act(self) -> None:
        label, clickable = action(self.item)
        if clickable:
            self._on_change(self.item, label == ACTION_LABELS[0])
