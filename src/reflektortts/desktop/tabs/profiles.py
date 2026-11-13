"""The Profiles tab: every profile, bundled and the user's own, with its state; the selected one's
details; buttons to enable or disable the profile, open its app's settings window, open a window for
the integrations its sources need, copy a bundled one to edit, remove one of the user's own, import a
profile file, read the files again after editing them, and open the user's folder.

The buttons never move: the one that enables or disables is as wide as its longest label, and a
button that does not apply to the selected profile is grayed out."""

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from reflektortts.desktop.api.integrations import IntegrationItem, integrations_hint, integrations_of
from reflektortts.desktop.api.profiles import (
    ORIGINS,
    STATES,
    ProfileItem,
    details_text,
    file_name,
    languages_column_text,
    name_text,
    overlay_text,
    rating_text,
    summary_text,
)
from reflektortts.desktop.tabs.integration_window import IntegrationWindow
from reflektortts.desktop.tabs.medals import GAP, MEDALS, medal_photo
from reflektortts.desktop.widgets.status_bar import StatusBar
from reflektortts.desktop.widgets.tables import (
    button_width,
    fit_columns,
    fit_tree_column,
    flat_treeview_style,
    row_image_size,
)
from reflektortts.desktop.widgets.theme import BUSY, DIM, GOOD, group_background, heading_font

DETAILS_LINES = 6
RATING = "Rating"
"""The first column's title: the profile's medal."""
COLUMNS = (
    ("name", "Name"),
    ("tested", "Tested languages"),
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
    "not_set_up": BUSY,
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
        on_app_settings: Callable[[ProfileItem], None],
        app_settings_missing: str | None,
        on_copy: Callable[[ProfileItem], None],
        on_remove: Callable[[ProfileItem], None],
        on_import: Callable[[], None],
        on_reload: Callable[[], None],
        on_open_folder: Callable[[], None],
        on_integration: Callable[[IntegrationItem, bool], None],
        languages_text: Callable[[Sequence[str]], str],
    ) -> None:
        """app_settings_missing: why the settings window cannot be opened, or None when it can.
        on_integration is given an integration and whether to enable it."""
        self._languages_text = languages_text
        self.frame = ttk.Frame(parent, padding=(8, 8, 8, 6))
        self._status_bar = status_bar
        self._on_enable = on_enable
        self._on_app_settings = on_app_settings
        self._app_settings_missing = app_settings_missing
        self._on_copy = on_copy
        self._on_integration = on_integration
        self._integration_window: IntegrationWindow | None = None
        self._integration_profile: str | None = None
        """The profile the integration window is open for."""
        self._on_remove = on_remove
        self._items: dict[str, ProfileItem] = {}
        self._integrations: list[IntegrationItem] = []
        self.frame.columnconfigure(0, weight=1)
        # The list and the box under it share the height 60/40 as the window is resized.
        self.frame.rowconfigure(0, weight=3, uniform="split")
        self.frame.rowconfigure(2, weight=2, uniform="split")
        self._build_table()
        self._build_details(on_import, on_reload, on_open_folder)

    def _build_table(self) -> None:
        table = ttk.Frame(self.frame)
        table.grid(row=0, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._tree = ttk.Treeview(
            table,
            columns=[column for column, _ in COLUMNS],
            show="tree headings",
            selectmode="browse",
            style=flat_treeview_style(),
        )
        # Images can only be in the first column, so the medals are there.
        self._medal_size = row_image_size()
        self._medals = {rating: medal_photo(rating, self._medal_size) for rating in (*MEDALS, None)}
        self._tree.heading("#0", text=RATING, anchor="w")
        self._tree.column("#0", stretch=False)
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

    def _build_details(
        self, on_import: Callable[[], None], on_reload: Callable[[], None], on_open_folder: Callable[[], None]
    ) -> None:
        header = ttk.Frame(self.frame)
        header.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self._title = ttk.Label(header, text="", font=heading_font())
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = ttk.Label(header, text="", foreground=DIM)
        self._subtitle.grid(row=1, column=0, sticky="w")

        group = ttk.LabelFrame(self.frame, text="Details", padding=(8, 2, 2, 4))
        group.grid(row=2, column=0, sticky="nsew")
        group.columnconfigure(0, weight=1)
        group.rowconfigure(0, weight=1)
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
        self._app_settings = ttk.Button(
            buttons, text="App settings…", state="disabled", command=self._open_app_settings
        )
        self._app_settings.grid(row=0, column=1, padx=(6, 0))
        self._integration = ttk.Button(buttons, text="Integration…", state="disabled", command=self._open_integration)
        self._integration.grid(row=0, column=2, padx=(6, 0))
        self._copy = ttk.Button(buttons, text="Copy to edit", state="disabled", command=self._copy_selected)
        self._copy.grid(row=0, column=3, padx=(6, 0))
        self._remove = ttk.Button(buttons, text="Remove", state="disabled", command=self._remove_selected)
        self._remove.grid(row=0, column=4, padx=(6, 0))
        import_button = ttk.Button(buttons, text="Import…", command=on_import)
        import_button.grid(row=0, column=5, padx=(6, 0))
        reload = ttk.Button(buttons, text="Reload", command=on_reload)
        reload.grid(row=0, column=6, padx=(6, 0))
        folder = ttk.Button(buttons, text="Open profiles folder", command=on_open_folder)
        folder.grid(row=0, column=7, padx=(6, 0))
        self._status_bar.hint(self._button, self._button_hint)
        self._status_bar.hint(self._app_settings, self._app_settings_hint)
        self._status_bar.hint(self._integration, self._integration_hint)
        self._status_bar.hint(
            self._copy, lambda: "Copy a bundled profile to your folder and show it there, to edit it in an editor."
        )
        self._status_bar.hint(self._remove, self._remove_hint)
        self._status_bar.hint(import_button, lambda: "Add a profile file to your own, once it is checked.")
        self._status_bar.hint(reload, lambda: "Read the profile files again, after editing them.")
        self._status_bar.hint(folder, lambda: "Open the folder for your own profiles, which replace bundled ones.")

    def show_message(self, message: str) -> None:
        """Shows a message in place of the profiles, e.g. while they load."""
        self._tree.delete(*self._tree.get_children())
        for index, line in enumerate(message.splitlines()):  # A row holds one line.
            iid = "message" if index == 0 else f"message-{index}"
            self._tree.insert("", "end", iid=iid, values=(line, "", "", "", "", ""), tags=("message",))
        self._items = {}
        self._fit_columns()
        self._status_bar.set_text(self.frame, "")
        self._show_selected()

    def show(self, items: list[ProfileItem], integrations: list[IntegrationItem]) -> None:
        """Shows the profiles, sorted by name, keeping the selection, with the integrations their
        sources need."""
        selected = self._selected_id()
        self._integrations = integrations
        self._tree.delete(*self._tree.get_children())
        self._items = {item.id: item for item in sorted(items, key=lambda item: name_text(item).lower())}
        for item in self._items.values():
            executables = ", ".join(executable.name for executable in item.executables)
            values = (
                name_text(item),
                languages_column_text(item),
                ORIGINS[item.origin],
                executables,
                overlay_text(item),
                STATES[item.state],
            )
            medal, _ = rating_text(item)
            # A broken file has no medal, nor its image ("" is none).
            image = self._medals[item.rating] if medal else ""
            self._tree.insert("", "end", iid=item.id, text=medal, image=image, values=values, tags=(item.state,))
        if selected in self._items:
            self._tree.selection_set(selected)
            self._tree.see(selected)
        self._fit_columns()
        self._status_bar.set_text(self.frame, summary_text(items))
        self._show_selected()
        self._follow_integrations()

    def _fit_columns(self) -> None:
        fit_tree_column(self._tree, RATING, self._medal_size + GAP)
        fit_columns(self._tree, COLUMNS)

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
            self._details.insert("1.0", details_text(item, lambda code: self._languages_text((code,))))
        self._details.configure(state="disabled")
        self._integration.configure(state="normal" if integrations_of(item, self._integrations) else "disabled")
        self._app_settings.configure(state="normal" if self._can_open_app_settings(item) else "disabled")
        self._copy.configure(state="normal" if item is not None and item.origin == "bundled" else "disabled")
        self._remove.configure(state="normal" if item is not None and item.origin != "bundled" else "disabled")
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
            return "A broken profile is not used: fix its file, or remove it."
        if item.state == "disabled":
            return "Use this profile again."
        return "Stop using this profile: its app is not read until it is enabled again."

    def _can_open_app_settings(self, item: ProfileItem | None) -> bool:
        return self._app_settings_missing is None and item is not None and item.state != "broken"

    def _app_settings_hint(self) -> str:
        if self._app_settings_missing is not None:
            return self._app_settings_missing
        item = self._selected()
        if item is not None and item.state == "broken":
            return "A broken profile has no settings: fix its file, or remove it."
        return "Change this app’s voice, languages and the rest, also while it isn’t running."

    def _integration_hint(self) -> str:
        return integrations_hint(integrations_of(self._selected(), self._integrations))

    def _open_integration(self) -> None:
        item = self._selected()
        integrations = integrations_of(item, self._integrations)
        if item is None or not integrations or self._integration_window is not None:
            return
        self._integration_profile = item.id
        self._integration_window = IntegrationWindow(
            self.frame,
            f"{name_text(item)}: {'integrations' if len(integrations) > 1 else 'integration'}",
            integrations,
            self._on_integration,
            self._integration_closed,
        )

    def close_integration(self) -> None:
        """Closes the integration window, if it is open."""
        if self._integration_window is not None:
            self._integration_window.close()

    def _integration_closed(self) -> None:
        self._integration_window = None
        self._integration_profile = None

    def _follow_integrations(self) -> None:
        """Shows the open integration window the new state, or closes it if its profile is gone or
        needs other integrations now."""
        window = self._integration_window
        if window is None:
            return
        profile = self._items.get(self._integration_profile or "")
        integrations = integrations_of(profile, self._integrations)
        if [integration.id for integration in integrations] == window.ids:
            window.show(integrations)
        else:
            window.close()

    def _remove_hint(self) -> str:
        item = self._selected()
        if item is not None and item.origin == "override":
            return "Delete your own file: the bundled profile is used again."
        return "Delete your own profile file."

    def _open_app_settings(self) -> None:
        item = self._selected()
        if self._can_open_app_settings(item) and item is not None:
            self._on_app_settings(item)

    def _copy_selected(self) -> None:
        item = self._selected()
        if item is not None and item.origin == "bundled":
            self._on_copy(item)

    def _remove_selected(self) -> None:
        item = self._selected()
        if item is not None and item.origin != "bundled":
            self._on_remove(item)

    def _act(self) -> None:
        item = self._selected()
        if item is not None and item.state != "broken":
            self._on_enable(item, item.state == "disabled")
