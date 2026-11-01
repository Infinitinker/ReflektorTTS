"""The desktop app's window: a Status tab (what ReflektorTTS is doing, pause, its folders) and one
tab per kind of download (voices, translations)."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.catalog import DownloadItem
from reflektortts.desktop.downloads_tab import DownloadsTab
from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.status import CoreStatus, describe
from reflektortts.downloads.source import Kind

SIZE = (800, 450)
"""At start, and the smallest; the window can grow."""
PADDING = 16
ICON_SIZES = (16, 32, 48, 256)
"""For the title bar, the taskbar and Alt+Tab; the system picks the size it needs."""
DOWNLOAD_TABS = {Kind.VOICE: "Voices", Kind.TRANSLATION: "Translations"}
"""The title of each kind of download's tab."""


class Window:
    def __init__(
        self,
        root: tk.Tk,
        on_pause_toggle: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_close: Callable[[], None],
        on_downloads_opened: Callable[[], None],
        on_download: Callable[[DownloadItem], None],
        on_remove: Callable[[DownloadItem], None],
        language_name: Callable[[str], str],
    ) -> None:
        self._root = root
        root.title("ReflektorTTS")
        # Kept here: Tkinter drops an image nothing in Python refers to.
        self._icons = [icon_photo(size) for size in ICON_SIZES]
        root.iconphoto(True, *self._icons)
        root.geometry(f"{SIZE[0]}x{SIZE[1]}")
        root.minsize(*SIZE)
        root.protocol("WM_DELETE_WINDOW", on_close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(root)
        self._notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        status = ttk.Frame(self._notebook, padding=PADDING)
        self._notebook.add(status, text="Status")
        self._build_status(status, on_pause_toggle, on_open_logs, on_open_settings)

        self.downloads: dict[str, DownloadsTab] = {}
        """Each kind's tab, by the kind's name in the API."""
        for kind, title in DOWNLOAD_TABS.items():
            tab = DownloadsTab(self._notebook, on_download, on_remove, language_name)
            self._notebook.add(tab.frame, text=title)
            self.downloads[kind.value] = tab
        self._notebook.bind("<<NotebookTabChanged>>", lambda event: self._tab_changed(on_downloads_opened))

    def show_status(self, status: CoreStatus | None) -> None:
        self._status.configure(text=describe(status))
        self._pause.configure(
            text="Resume reading" if status is not None and status.paused else "Pause reading",
            state="disabled" if status is None else "normal",
        )

    def show_stopped(self, message: str) -> None:
        self._status.configure(text=message)
        self._pause.configure(state="disabled")

    def show(self) -> None:
        """Shows the window on its Status tab."""
        self._notebook.select(0)  # type: ignore[no-untyped-call]  # Untyped in typeshed.
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def hide(self) -> None:
        self._root.withdraw()

    def _build_status(
        self,
        frame: ttk.Frame,
        on_pause_toggle: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_settings: Callable[[], None],
    ) -> None:
        self._status = ttk.Label(frame, text=describe(None))
        self._status.grid(row=0, column=0, columnspan=2, sticky="w")
        self._pause = ttk.Button(frame, text="Pause reading", command=on_pause_toggle, state="disabled")
        self._pause.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        hint = "In a game, open the ReflektorTTS panel with Ctrl+Shift+R."
        ttk.Label(frame, text=hint).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 12))
        ttk.Button(frame, text="Open logs folder", command=on_open_logs).grid(row=3, column=0, sticky="w")
        ttk.Button(frame, text="Open settings folder", command=on_open_settings).grid(
            row=3, column=1, sticky="w", padx=(8, 0)
        )

    def _tab_changed(self, on_downloads_opened: Callable[[], None]) -> None:
        if self._notebook.index("current") > 0:  # type: ignore[no-untyped-call]  # Untyped in typeshed.
            on_downloads_opened()
