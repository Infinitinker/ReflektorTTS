"""The Profiles tab: every profile, bundled and the user's own, with its state; the selected one's
details, and buttons to enable or disable it and to open the user's profiles folder.

The buttons never move: the one that enables or disables is as wide as its longest label, and is
grayed out for a broken file."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.profiles import (
    ORIGINS,
    STATES,
    ProfileItem,
    details_text,
    file_name,
    name_text,
    overlay_text,
    summary_text,
)
from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import BUSY, DIM, GOOD, group_background, heading_font
from reflektortts.desktop.widgets import button_width, fit_columns

DETAILS_LINES = 6
COLUMNS = (
    ("name", "Name"),
    ("origin", "Origin"),
    ("executables", "Executables"),
    ("overlay", "Overlay"),
    ("state", "State"),
)
ENABLE_LABELS = ("Enable", "Disable")
STATE_COLORS = {
    "reading": GOOD,
    "disabled": DIM,
    "unsupported": BUSY,
    "not_used": BUSY,
    "clash": BUSY,
    "broken": BUSY,
}
"""Text color per state: green while read, gray when disabled, amber where something needs the
user's attention; others have the default color."""


class ProfilesTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        status_bar: StatusBar,
        on_enable: Callable[[ProfileItem, bool], None],
        on_open_folder: Callable[[], None],
    ) -> None:
        self.frame = ttk.Frame(parent, padding=(8, 8, 8, 6))
        self._status_bar = status_bar
        self._on_enable = on_enable
        self._items: dict[str, ProfileItem] = {}
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        self._build_table()
        self._build_details(on_open_folder)

    def _build_table(self) -> None:
        table = ttk.Frame(self.frame)
        table.grid(row=0, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._tree = ttk.Treeview(
            table, columns=[column for column, _ in COLUMNS], show="headings", selectmode="browse"
        )
        for column, title in COLUMNS:
            self._tree.heading(column, text=title, anchor="w")
            self._tree.column(column, anchor="w", stretch=column == "state")
        for state, color in STATE_COLORS.items():
            self._tree.tag_configure(state, foreground=color)
        self._tree.tag_configure("message", foreground=DIM)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", lambda event: self._show_selected())

    def _build_details(self, on_open_folder: Callable[[], None]) -> None:
        header = ttk.Frame(self.frame)
        header.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self._title = ttk.Label(header, text="", font=heading_font())
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = ttk.Label(header, text="", foreground=DIM)
        self._subtitle.grid(row=1, column=0, sticky="w")

        group = ttk.LabelFrame(self.frame, text="Details", padding=(8, 2, 2, 4))
        group.grid(row=2, column=0, sticky="ew")
        group.columnconfigure(0, weight=1)
        self._details = tk.Text(
            group,
            height=DETAILS_LINES,
            wrap="word",
            font="TkDefaultFont",
            background=group_background(),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            state="disabled",
        )
        self._details.grid(row=0, column=0, sticky="nsew")
        details_scroll = ttk.Scrollbar(group, orient="vertical", command=self._details.yview)
        self._details.configure(yscrollcommand=details_scroll.set)
        details_scroll.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self.frame)
        buttons.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._button = ttk.Button(
            buttons, text="Disable", width=button_width(ENABLE_LABELS), state="disabled", command=self._act
        )
        self._button.grid(row=0, column=0)
        folder = ttk.Button(buttons, text="Open profiles folder", command=on_open_folder)
        folder.grid(row=0, column=1, padx=(6, 0))
        self._status_bar.hint(self._button, self._button_hint)
        self._status_bar.hint(folder, lambda: "Open the folder for your own profiles, which replace bundled ones.")

    def show_message(self, message: str) -> None:
        """Shows a message in place of the profiles, e.g. while they load."""
        self._tree.delete(*self._tree.get_children())
        self._tree.insert("", "end", iid="message", values=(message, "", "", "", ""), tags=("message",))
        self._items = {}
        fit_columns(self._tree, COLUMNS)
        self._status_bar.set_text(self.frame, "")
        self._show_selected()

    def show(self, items: list[ProfileItem]) -> None:
        """Shows the profiles, sorted by name, keeping the selection."""
        selected = self._selected_id()
        self._tree.delete(*self._tree.get_children())
        self._items = {item.id: item for item in sorted(items, key=lambda item: name_text(item).lower())}
        for item in self._items.values():
            executables = ", ".join(executable.name for executable in item.executables)
            values = (name_text(item), ORIGINS[item.origin], executables, overlay_text(item), STATES[item.state])
            self._tree.insert("", "end", iid=item.id, values=values, tags=(item.state,))
        if selected in self._items:
            self._tree.selection_set(selected)
            self._tree.see(selected)
        fit_columns(self._tree, COLUMNS)
        self._status_bar.set_text(self.frame, summary_text(items))
        self._show_selected()

    def _selected_id(self) -> str | None:
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _selected(self) -> ProfileItem | None:
        selected = self._selected_id()
        return self._items.get(selected) if selected else None

    def _show_selected(self) -> None:
        item = self._selected()
        self._title.configure(text="" if item is None else name_text(item))
        self._subtitle.configure(text="" if item is None else f"{ORIGINS[item.origin]}, {file_name(item)}")
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        if item is not None:
            self._details.insert("1.0", details_text(item))
        self._details.configure(state="disabled")
        if item is None or item.state == "broken":
            self._button.configure(text="Disable", state="disabled")
        elif item.state == "disabled":
            self._button.configure(text="Enable", state="normal")
        else:
            self._button.configure(text="Disable", state="normal")

    def _button_hint(self) -> str:
        item = self._selected()
        if item is None:
            return ""
        if item.state == "broken":
            return "A broken profile is not used; fix its file, or remove it."
        if item.state == "disabled":
            return "Use this profile again."
        return "Stop using this profile: its app is not read until it is enabled again."

    def _act(self) -> None:
        item = self._selected()
        if item is not None and item.state != "broken":
            self._on_enable(item, item.state == "disabled")
