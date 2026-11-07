"""The desktop app's window: a Status tab (what ReflektorTTS is doing, pause, its folders, and on
Windows whether it starts with Windows), one tab per kind of download (voices, translations) and a
status bar."""

import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.catalog import DownloadItem
from reflektortts.desktop.downloads_tab import DownloadsTab
from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.profiles import ProfileItem
from reflektortts.desktop.profiles_tab import ProfilesTab
from reflektortts.desktop.status import CoreStatus, describe, hint
from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import BUSY, DIM, GOOD, heading_font
from reflektortts.desktop.widgets import button_width
from reflektortts.downloads.source import Kind

SIZE = (800, 600)
"""At start, and the smallest; the window can grow."""
PADDING = 16
ICON_SIZES = (16, 32, 48, 256)
"""For the title bar, the taskbar and Alt+Tab; the system picks the size it needs."""
PAUSE_LABELS = ("Pause reading", "Resume reading")
"""The pause button's labels; it is as wide as the longer, so the buttons after it never move."""
DOWNLOAD_TABS = {Kind.VOICE: "Voices", Kind.TRANSLATION: "Translations"}
"""The title of each kind of download's tab."""


def status_color(status: CoreStatus | None) -> str:
    """Green while an app is read, amber while paused or for an unsupported version; empty for the
    default color."""
    if status is None:
        return DIM
    if status.paused or (status.unsupported and not status.app):
        return BUSY
    return GOOD if status.app else ""


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
        on_preview: Callable[[DownloadItem], None],
        language_name: Callable[[str], str],
        on_profiles_opened: Callable[[], None],
        on_enable_profile: Callable[[ProfileItem, bool], None],
        on_copy_profile: Callable[[ProfileItem], None],
        on_remove_profile: Callable[[ProfileItem], None],
        on_import_profile: Callable[[], None],
        on_reload_profiles: Callable[[], None],
        on_open_profiles: Callable[[], None],
        on_start_with_windows: Callable[[bool], None],
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
        self._notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 6))
        self._status_bar = StatusBar(root, row=1)
        status = ttk.Frame(self._notebook, padding=PADDING)
        self._notebook.add(status, text="Status")
        self._build_status(status, on_pause_toggle, on_open_logs, on_open_settings, on_start_with_windows)
        self.profiles = ProfilesTab(
            self._notebook,
            self._status_bar,
            on_enable_profile,
            on_copy_profile,
            on_remove_profile,
            on_import_profile,
            on_reload_profiles,
            on_open_profiles,
        )
        self._notebook.add(self.profiles.frame, text="Profiles")

        self.downloads: dict[str, DownloadsTab] = {}
        """Each kind's tab, by the kind's name in the API."""
        for kind, title in DOWNLOAD_TABS.items():
            # Only voices can be heard before use.
            preview = on_preview if kind == Kind.VOICE else None
            tab = DownloadsTab(self._notebook, self._status_bar, on_download, on_remove, preview, language_name)
            self._notebook.add(tab.frame, text=title)
            self.downloads[kind.value] = tab
        self._notebook.bind(
            "<<NotebookTabChanged>>", lambda event: self._tab_changed(on_profiles_opened, on_downloads_opened)
        )

    def show_status(self, status: CoreStatus | None) -> None:
        self._paused = status is not None and status.paused
        self._status.configure(text=describe(status), foreground=status_color(status))
        self._hint.configure(text=hint(status))
        self._pause.configure(
            text=PAUSE_LABELS[1] if self._paused else PAUSE_LABELS[0],
            state="disabled" if status is None else "normal",
        )

    def show_stopped(self, message: str) -> None:
        self._status.configure(text=message, foreground=DIM)
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
        on_start_with_windows: Callable[[bool], None],
    ) -> None:
        self._status = ttk.Label(frame, text=describe(None), font=heading_font(), foreground=status_color(None))
        self._status.grid(row=0, column=0, sticky="w")
        self._hint = ttk.Label(frame, text=hint(None), foreground=DIM)
        self._hint.grid(row=1, column=0, sticky="w", pady=(4, 16))

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="w")
        self._paused = False
        self._pause = ttk.Button(
            buttons,
            text=PAUSE_LABELS[0],
            width=button_width(PAUSE_LABELS),
            command=on_pause_toggle,
            state="disabled",
        )
        self._pause.grid(row=0, column=0)
        logs = ttk.Button(buttons, text="Open logs folder", command=on_open_logs)
        logs.grid(row=0, column=1, padx=(6, 0))
        settings = ttk.Button(buttons, text="Open settings folder", command=on_open_settings)
        settings.grid(row=0, column=2, padx=(6, 0))
        self._status_bar.hint(self._pause, self._pause_hint)
        self._status_bar.hint(logs, lambda: "Open the folder with ReflektorTTS's logs, e.g. to report a problem.")
        self._status_bar.hint(settings, lambda: "Open the folder with the settings saved for each app.")

        self._start_with_windows = tk.BooleanVar(value=False)
        self._autostart = ttk.Checkbutton(
            frame,
            text="Start with Windows",
            variable=self._start_with_windows,
            command=lambda: on_start_with_windows(self._start_with_windows.get()),
            state="disabled",
        )
        if sys.platform == "win32":
            self._autostart.grid(row=3, column=0, sticky="w", pady=(16, 0))
        self._autostart_available = False
        self._status_bar.hint(self._autostart, self._autostart_hint)

    def show_start_with_windows(self, enabled: bool | None) -> None:
        """Whether ReflektorTTS starts with Windows; None where it cannot."""
        self._autostart_available = enabled is not None
        self._start_with_windows.set(bool(enabled))
        self._autostart.configure(state="normal" if self._autostart_available else "disabled")

    def _autostart_hint(self) -> str:
        if self._autostart_available:
            return "Start ReflektorTTS, hidden next to the clock, when you sign in to Windows."
        return "Only ReflektorTTS.exe from a release can start with Windows."

    def _pause_hint(self) -> str:
        return "Read lines aloud again." if self._paused else "Stop reading lines aloud until you resume."

    def profiles_shown(self) -> bool:
        """Whether the window is open on the Profiles tab."""
        current = str(self._notebook.select())  # type: ignore[no-untyped-call]  # Untyped in typeshed.
        return self._root.state() != "withdrawn" and current == str(self.profiles.frame)

    def _tab_changed(self, on_profiles_opened: Callable[[], None], on_downloads_opened: Callable[[], None]) -> None:
        current = str(self._notebook.select())  # type: ignore[no-untyped-call]  # Untyped in typeshed.
        self._status_bar.show_page(current)
        if current == str(self.profiles.frame):
            on_profiles_opened()
        elif current in {str(tab.frame) for tab in self.downloads.values()}:
            on_downloads_opened()
