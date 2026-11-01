"""A tab of downloads of one kind (voices, or translations): a table, the selected entry's name,
license and buttons to download or remove it, to open its page and, for voices, to hear it.

The buttons never move: the one that downloads or removes is as wide as its longest label, and a
button that cannot be used for the selected entry is grayed out."""

import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.catalog import DownloadItem, DownloadProgress, size_text, state_text, summary_text
from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import BUSY, DIM, GOOD, group_background, heading_font

LICENSE_LINES = 6
NO_LICENSE = "The license is not published with this list. Open its page to read about it."
COLUMNS = (("name", "Name"), ("source", "Source"), ("languages", "Languages"), ("size", "Size"), ("state", "State"))
COLUMN_PADDING = 24
"""Pixels added to the widest text of a column."""
ACTION_LABELS = ("Download", "Downloading…", "Remove")
PREVIEW_LABELS = ("Preview", "Playing…")


def _width(labels: tuple[str, ...]) -> int:
    """A button's width for its longest label, so it never changes; in average character widths,
    so a little room is left for wider letters."""
    return max(len(label) for label in labels) + 2


class DownloadsTab:
    def __init__(
        self,
        parent: ttk.Notebook,
        status_bar: StatusBar,
        on_download: Callable[[DownloadItem], None],
        on_remove: Callable[[DownloadItem], None],
        on_preview: Callable[[DownloadItem], None] | None,
        language_name: Callable[[str], str],
    ) -> None:
        """on_preview is None for downloads that cannot be heard."""
        self.frame = ttk.Frame(parent, padding=(8, 8, 8, 6))
        self._status_bar = status_bar
        self._on_download = on_download
        self._on_remove = on_remove
        self._on_preview = on_preview
        self._playing: str | None = None
        """The voice whose preview is loading or playing."""
        self._language_name = language_name
        self._items: dict[str, DownloadItem] = {}
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        self._build_table()
        self._build_details()

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
        self._tree.tag_configure("installed", foreground=GOOD)
        self._tree.tag_configure("downloading", foreground=BUSY)
        self._tree.tag_configure("message", foreground=DIM)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", lambda event: self._show_selected())

    def _build_details(self) -> None:
        header = ttk.Frame(self.frame)
        header.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self._title = ttk.Label(header, text="", font=heading_font())
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = ttk.Label(header, text="", foreground=DIM)
        self._subtitle.grid(row=1, column=0, sticky="w")

        group = ttk.LabelFrame(self.frame, text="License", padding=(8, 2, 2, 4))
        group.grid(row=2, column=0, sticky="ew")
        group.columnconfigure(0, weight=1)
        self._license = tk.Text(
            group,
            height=LICENSE_LINES,
            wrap="word",
            font="TkDefaultFont",
            background=group_background(),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            state="disabled",
        )
        self._license.grid(row=0, column=0, sticky="nsew")
        license_scroll = ttk.Scrollbar(group, orient="vertical", command=self._license.yview)
        self._license.configure(yscrollcommand=license_scroll.set)
        license_scroll.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self.frame)
        buttons.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._button = ttk.Button(
            buttons, text="Download", width=_width(ACTION_LABELS), state="disabled", command=self._act
        )
        self._button.grid(row=0, column=0)
        self._page = ttk.Button(buttons, text="Open page", state="disabled", command=self._open_page)
        self._page.grid(row=0, column=1, padx=(6, 0))
        self._status_bar.hint(self._button, self._button_hint)
        self._status_bar.hint(self._page, lambda: "Open its page in your browser, e.g. to read more about its license.")
        self._preview: ttk.Button | None = None
        if self._on_preview is not None:
            self._preview = ttk.Button(
                buttons, text="Preview", width=_width(PREVIEW_LABELS), state="disabled", command=self._play_preview
            )
            self._preview.grid(row=0, column=2, padx=(6, 0))
            self._status_bar.hint(self._preview, self._preview_hint)

    def show_message(self, message: str) -> None:
        """Shows a message in place of the entries, e.g. while they load."""
        self._tree.delete(*self._tree.get_children())
        self._tree.insert("", "end", iid="message", values=(message, "", "", "", ""), tags=("message",))
        self._items = {}
        self._fit_columns()
        self._status_bar.set_text(self.frame, "")
        self._show_selected()

    def show(self, items: list[DownloadItem]) -> None:
        """Shows the entries, sorted by language, keeping the selection."""
        selected = self._selected_id()
        self._tree.delete(*self._tree.get_children())
        self._items = {item.id: item for item in sorted(items, key=lambda item: (item.languages, item.name))}
        for item in self._items.values():
            self._tree.insert("", "end", iid=item.id, values=self._row(item), tags=(item.state,))
        if selected in self._items:
            self._tree.selection_set(selected)
            self._tree.see(selected)
        self._fit_columns()
        self._status_bar.set_text(self.frame, summary_text(items))
        self._show_selected()

    def show_preview(self, voice: str, playing: bool) -> None:
        """A voice's preview started (also while it loads) or ended; one plays at a time."""
        if playing:
            self._playing = voice
        elif self._playing == voice:
            self._playing = None
        self._show_selected()

    def show_progress(self, progress: DownloadProgress) -> None:
        if progress.id in self._items and progress.state == "downloading":
            self._show_downloading(progress.id, progress.done, progress.total)

    def _row(self, item: DownloadItem) -> tuple[str, str, str, str, str]:
        state = state_text(item.state, item.done, item.total)
        return item.name, item.source, self._languages(item), size_text(item.size), state

    def _languages(self, item: DownloadItem) -> str:
        return ", ".join(self._language_name(language) for language in item.languages)

    def _fit_columns(self) -> None:
        """Sizes each column to its widest text; the last one also takes the room left."""
        style = ttk.Style()
        font = tkfont.nametofont(style.lookup("Treeview", "font") or "TkDefaultFont")
        heading = tkfont.nametofont(style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
        rows = self._tree.get_children()
        for column, title in COLUMNS:
            texts = [str(self._tree.set(row, column)) for row in rows]
            width = max([heading.measure(title), *(font.measure(text) for text in texts)])
            self._tree.column(column, width=width + COLUMN_PADDING)

    def _show_downloading(self, item_id: str, done: int, total: int | None) -> None:
        self._tree.set(item_id, "state", state_text("downloading", done, total))
        self._tree.item(item_id, tags=("downloading",))
        self._show_selected()

    def _selected_id(self) -> str | None:
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _selected(self) -> DownloadItem | None:
        selected = self._selected_id()
        return self._items.get(selected) if selected else None

    def _downloading(self, item: DownloadItem) -> bool:
        return "downloading" in self._tree.item(item.id, "tags")

    def _show_selected(self) -> None:
        item = self._selected()
        self._title.configure(text="" if item is None else item.name)
        details = [] if item is None else [self._languages(item), size_text(item.size)]
        self._subtitle.configure(text=", ".join(detail for detail in details if detail))
        self._license.configure(state="normal")
        self._license.delete("1.0", "end")
        if item is not None:
            self._license.insert("1.0", item.license or NO_LICENSE)
        self._license.configure(state="disabled")
        self._page.configure(state="normal" if item is not None and item.page else "disabled")
        if self._preview is not None:
            if item is not None and item.id == self._playing:
                self._preview.configure(text="Playing…", state="disabled")
            else:
                installed = item is not None and item.state == "installed"
                self._preview.configure(text="Preview", state="normal" if installed else "disabled")
        if item is None:
            self._button.configure(text="Download", state="disabled")
        elif self._downloading(item):
            self._button.configure(text="Downloading…", state="disabled")
        elif item.state == "installed":
            self._button.configure(text="Remove", state="normal" if item.removable else "disabled")
        else:
            self._button.configure(text="Download", state="normal")

    def _button_hint(self) -> str:
        item = self._selected()
        if item is None:
            return ""
        if self._downloading(item):
            return "It is being downloaded."
        if item.state == "installed":
            if not item.removable:
                return "It was not downloaded here, so it cannot be removed here."
            return "Delete it from this computer. It can be downloaded again."
        return "Download it. It can be used right away, even in a game that is running."

    def _preview_hint(self) -> str:
        item = self._selected()
        if item is None or item.state != "installed":
            return "Hear a sentence in this voice, once it is installed."
        return "Hear a sentence in this voice, even while a game is read."

    def _play_preview(self) -> None:
        item = self._selected()
        if item is not None and self._on_preview is not None:
            self.show_preview(item.id, True)
            self._on_preview(item)

    def _act(self) -> None:
        item = self._selected()
        if item is None:
            return
        if item.state == "installed":
            self._on_remove(item)
        else:
            self._show_downloading(item.id, 0, item.size)
            self._on_download(item)

    def _open_page(self) -> None:
        item = self._selected()
        if item is not None:
            webbrowser.open(item.page)
