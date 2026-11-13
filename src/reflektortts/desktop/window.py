"""The ReflektorTTS window: a Status tab, a Profiles tab, one tab per kind of download (voices,
translations), a Settings tab and a status bar."""

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from reflektortts.desktop.about import About
from reflektortts.desktop.api.catalog import DownloadItem
from reflektortts.desktop.api.integrations import IntegrationItem
from reflektortts.desktop.api.profiles import ProfileItem
from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.tabs.downloads import DownloadsTab
from reflektortts.desktop.tabs.profiles import ProfilesTab
from reflektortts.desktop.tabs.settings import SettingsTab
from reflektortts.desktop.tabs.status import StatusTab
from reflektortts.desktop.widgets.status_bar import StatusBar
from reflektortts.downloads.source import Kind

SIZE = (800, 600)
"""At start, and the smallest; the window can grow."""
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
        on_preview: Callable[[DownloadItem], None],
        languages_text: Callable[[Sequence[str]], str],
        speech_rules_text: Callable[[str], str],
        voice_title: Callable[[str], str],
        on_profiles_opened: Callable[[], None],
        on_enable_profile: Callable[[ProfileItem, bool], None],
        on_app_settings: Callable[[ProfileItem], None],
        on_read_app_settings: Callable[[str, str], None],
        app_settings_missing: str | None,
        on_copy_profile: Callable[[ProfileItem], None],
        on_remove_profile: Callable[[ProfileItem], None],
        on_import_profile: Callable[[], None],
        on_reload_profiles: Callable[[], None],
        on_open_profiles: Callable[[], None],
        on_integration: Callable[[IntegrationItem, bool], None],
        on_start_with_windows: Callable[[bool], None],
        on_quit: Callable[[], None],
        on_open_link: Callable[[str], None],
        about: About,
        files_text: str,
        autostart_supported: bool,
        has_tray: bool,
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
        self.status = StatusTab(
            self._notebook,
            self._status_bar,
            on_pause_toggle,
            on_read_app_settings,
            app_settings_missing,
            on_quit,
            on_open_link,
            about,
            languages_text,
            voice_title,
            has_tray,
        )
        self._notebook.add(self.status.frame, text="Status")
        self.profiles = ProfilesTab(
            self._notebook,
            self._status_bar,
            on_enable_profile,
            on_app_settings,
            app_settings_missing,
            on_copy_profile,
            on_remove_profile,
            on_import_profile,
            on_reload_profiles,
            on_open_profiles,
            on_integration,
            languages_text,
        )
        self._notebook.add(self.profiles.frame, text="Profiles")

        self.downloads: dict[str, DownloadsTab] = {}
        """Each kind's tab, by the kind's name in the API."""
        for kind, title in DOWNLOAD_TABS.items():
            # Only voices can be heard before use.
            preview = on_preview if kind == Kind.VOICE else None
            tab = DownloadsTab(
                self._notebook, self._status_bar, on_download, on_remove, preview, languages_text, speech_rules_text
            )
            self._notebook.add(tab.frame, text=title)
            self.downloads[kind.value] = tab
        self.settings = SettingsTab(
            self._notebook,
            self._status_bar,
            files_text,
            autostart_supported,
            on_start_with_windows,
            on_open_settings,
            on_open_logs,
            on_open_profiles,
        )
        self._notebook.add(self.settings.frame, text="Settings")
        self._notebook.bind(
            "<<NotebookTabChanged>>", lambda event: self._tab_changed(on_profiles_opened, on_downloads_opened)
        )

    def show(self) -> None:
        """Shows the window on its Status tab."""
        self.profiles.close_integration()  # It would stay over another tab, no longer updated.
        self._notebook.select(0)  # type: ignore[no-untyped-call]  # Untyped in typeshed.
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def hide(self) -> None:
        self._root.withdraw()

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
