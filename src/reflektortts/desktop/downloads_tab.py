"""A tab of downloads of one kind (voices, or translations): a table, the selected entry's licence
and page, and the button to download or remove it."""

import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.catalog import DownloadItem, DownloadProgress, size_text, state_text

DETAILS_LINES = 7
NO_LICENCE = "The licence is not published with this list. Open its page to read about it."


class DownloadsTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        on_download: Callable[[DownloadItem], None],
        on_remove: Callable[[DownloadItem], None],
        language_name: Callable[[str], str],
    ) -> None:
        self.frame = ttk.Frame(parent, padding=8)
        self._on_download = on_download
        self._on_remove = on_remove
        self._language_name = language_name
        self._items: dict[str, DownloadItem] = {}
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)

        table = ttk.Frame(self.frame)
        table.grid(row=0, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._tree = ttk.Treeview(table, columns=("name", "languages", "size", "state"), show="headings")
        for column, title, width in (
            ("name", "Name", 340),
            ("languages", "Languages", 160),
            ("size", "Size", 80),
            ("state", "State", 160),
        ):
            self._tree.heading(column, text=title, anchor="w")
            self._tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", lambda event: self._show_selected())

        details = ttk.LabelFrame(self.frame, text="Licence", padding=8)
        details.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        details.columnconfigure(0, weight=1)
        self._licence = tk.Text(details, height=DETAILS_LINES, wrap="word", relief="flat", state="disabled")
        self._licence.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self._button = ttk.Button(details, text="Download", state="disabled", command=self._act)
        self._button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._page = ttk.Button(details, text="Open page", state="disabled", command=self._open_page)
        self._page.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))

    def show_message(self, message: str) -> None:
        """Shows a message in place of the entries, e.g. while they load."""
        self._tree.delete(*self._tree.get_children())
        self._tree.insert("", "end", iid="message", values=(message, "", "", ""))
        self._items = {}
        self._show_selected()

    def show(self, items: list[DownloadItem]) -> None:
        """Shows the entries, sorted by language, keeping the selection."""
        selected = self._selected_id()
        self._tree.delete(*self._tree.get_children())
        self._items = {item.id: item for item in sorted(items, key=lambda item: (item.languages, item.name))}
        for item in self._items.values():
            self._tree.insert("", "end", iid=item.id, values=self._row(item))
        if selected in self._items:
            self._tree.selection_set(selected)
        self._show_selected()

    def show_progress(self, progress: DownloadProgress) -> None:
        if progress.id in self._items and progress.state == "downloading":
            self._tree.set(progress.id, "state", state_text("downloading", progress.done, progress.total))
            self._show_selected()

    def _row(self, item: DownloadItem) -> tuple[str, str, str, str]:
        languages = ", ".join(self._language_name(language) for language in item.languages)
        return item.name, languages, size_text(item.size), state_text(item.state, item.done, item.total)

    def _selected_id(self) -> str | None:
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _selected(self) -> DownloadItem | None:
        selected = self._selected_id()
        return self._items.get(selected) if selected else None

    def _show_selected(self) -> None:
        item = self._selected()
        self._licence.configure(state="normal")
        self._licence.delete("1.0", "end")
        if item is not None:
            self._licence.insert("1.0", item.licence or NO_LICENCE)
        self._licence.configure(state="disabled")
        self._page.configure(state="disabled" if item is None else "normal")
        if item is None:
            self._button.configure(text="Download", state="disabled")
        elif self._tree.set(item.id, "state").startswith("Downloading"):
            self._button.configure(text="Downloading…", state="disabled")
        elif item.state == "installed":
            self._button.configure(text="Remove", state="normal")
        else:
            self._button.configure(text="Download", state="normal")

    def _act(self) -> None:
        item = self._selected()
        if item is None:
            return
        if item.state == "installed":
            self._on_remove(item)
        else:
            self._tree.set(item.id, "state", state_text("downloading", 0, item.size))
            self._show_selected()
            self._on_download(item)

    def _open_page(self) -> None:
        item = self._selected()
        if item is not None:
            webbrowser.open(item.page)
