"""The desktop app's window: a Status tab (what ReflektorTTS is doing, and about it), a Profiles tab,
one tab per kind of download (voices, translations), a Settings tab and a status bar."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.about import BUYCOFFEE, KO_FI, LICENSE, About
from reflektortts.desktop.catalog import DownloadItem
from reflektortts.desktop.clamped_label import ClampedLabel
from reflektortts.desktop.downloads_tab import DownloadsTab
from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.integrations import IntegrationItem
from reflektortts.desktop.profiles import ProfileItem
from reflektortts.desktop.profiles_tab import ProfilesTab
from reflektortts.desktop.settings_tab import SettingsTab
from reflektortts.desktop.status import (
    CoreStatus,
    describe,
    hint,
    languages_text,
    settings_caption,
    sound_text,
)
from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import BUSY, DIM, GOOD, heading_font, title_font
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
HEADER_ICON_SIZE = 48
DETAILS = ("Voice", "Languages", "App sound")
"""The lines under what ReflektorTTS is doing, in its Now box."""
NOW_PADDING = 12
HINT_LINES = 2
"""The line under the status always takes this many lines, so a long message never moves the details."""


def status_color(status: CoreStatus | None) -> str:
    """Green while an app is read, amber while paused or for an unsupported version; empty for the
    default color."""
    if status is None:
        return DIM
    if status.paused or (status.unsupported and not status.app):
        return BUSY
    return GOOD if status.app else ""


def hint_color(status: CoreStatus | None) -> str:
    """Amber when the line under the status says why a source of the app fails, else gray."""
    return BUSY if status is not None and status.app and status.source_error else DIM


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
        voice_title: Callable[[str], str],
        on_profiles_opened: Callable[[], None],
        on_enable_profile: Callable[[ProfileItem, bool], None],
        on_app_settings: Callable[[ProfileItem], None],
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
    ) -> None:
        self._root = root
        root.title("ReflektorTTS")
        # Kept here: Tkinter drops an image nothing in Python refers to.
        self._icons = [icon_photo(size) for size in ICON_SIZES]
        root.iconphoto(True, *self._icons)
        self._header_icon = icon_photo(HEADER_ICON_SIZE)
        self._language_name = language_name
        self._voice_title = voice_title
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
        self._build_status(status, on_pause_toggle, on_quit, on_open_link, about)
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

    def show_status(self, status: CoreStatus | None) -> None:
        self._paused = status is not None and status.paused
        self._status.configure(text=describe(status), foreground=status_color(status))
        self._hint.configure(text=hint(status), foreground=hint_color(status))
        texts = (
            ("", "", "")
            if status is None
            else (self._voice_title(status.voice), languages_text(status, self._language_name), sound_text(status))
        )
        for label, text in zip(self._details, texts, strict=True):
            label.configure(text=text)
        self._settings_for.configure(text=settings_caption(status))
        self._pause.configure(
            text=PAUSE_LABELS[1] if self._paused else PAUSE_LABELS[0],
            state="disabled" if status is None else "normal",
        )

    def show_stopped(self, message: str) -> None:
        self._status.configure(text=message, foreground=DIM)
        self._hint.configure(text="", foreground=DIM)
        self._settings_for.configure(text="")
        for label in self._details:
            label.configure(text="")
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
        on_quit: Callable[[], None],
        on_open_link: Callable[[str], None],
        about: About,
    ) -> None:
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, image=self._header_icon).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(header, text="ReflektorTTS", font=title_font()).grid(row=0, column=1, sticky="sw")
        ttk.Label(header, text=f"Your apps, read aloud. Version {about.version}", foreground=DIM).grid(
            row=1, column=1, sticky="nw"
        )
        quit_button = ttk.Button(header, text="Quit", command=on_quit)
        quit_button.grid(row=0, column=2, rowspan=2, sticky="e")
        self._status_bar.hint(
            quit_button,
            lambda: "Stop reading and close completely. Closing the window keeps it running next to the clock.",
        )

        now = ttk.LabelFrame(frame, text="Now", padding=NOW_PADDING)
        now.grid(row=1, column=0, sticky="ew")
        now.columnconfigure(1, weight=1)
        self._status = ttk.Label(now, text=describe(None), font=heading_font(), foreground=status_color(None))
        self._status.grid(row=0, column=0, columnspan=2, sticky="w")
        self._hint = ClampedLabel(now, HINT_LINES)
        self._hint.frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        self._hint.configure(text=hint(None), foreground=DIM)
        self._settings_for = ttk.Label(now, text="", foreground=DIM)
        self._settings_for.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self._details: list[ttk.Label] = []
        for row, name in enumerate(DETAILS, start=3):
            ttk.Label(now, text=name, foreground=DIM).grid(row=row, column=0, sticky="w", padx=(0, 16))
            detail = ttk.Label(now, text="")
            detail.grid(row=row, column=1, sticky="w")
            self._details.append(detail)
        self._paused = False
        self._pause = ttk.Button(
            now,
            text=PAUSE_LABELS[0],
            width=button_width(PAUSE_LABELS),
            command=on_pause_toggle,
            state="disabled",
        )
        self._pause.grid(row=3 + len(DETAILS), column=0, columnspan=2, sticky="w", pady=(12, 0))
        self._status_bar.hint(self._pause, self._pause_hint)

        links = ttk.Frame(frame)
        links.grid(row=3, column=0, sticky="ew")
        links.columnconfigure((0, 1), weight=1, uniform="links")
        project = ttk.LabelFrame(links, text="Project", padding=10)
        project.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        page = ttk.Button(project, text="Project page", command=lambda: on_open_link(about.project))
        page.grid(row=0, column=0)
        report = ttk.Button(project, text="Report a problem", command=lambda: on_open_link(about.issues))
        report.grid(row=0, column=1, padx=(6, 0))
        self._status_bar.hint(page, lambda: "Open the project's page on GitHub: its code, guides and releases.")
        self._status_bar.hint(
            report, lambda: "Report a problem on GitHub. The logs help: open their folder in the Settings tab."
        )

        support = ttk.LabelFrame(links, text="Support", padding=10)
        support.grid(row=0, column=1, sticky="nsew")
        ko_fi = ttk.Button(support, text="Ko-fi", command=lambda: on_open_link(KO_FI))
        ko_fi.grid(row=0, column=0)
        buycoffee = ttk.Button(support, text="buycoffee.to", command=lambda: on_open_link(BUYCOFFEE))
        buycoffee.grid(row=0, column=1, padx=(6, 0))
        self._status_bar.hint(ko_fi, lambda: "Buy the author a coffee on Ko-fi, with a card or PayPal.")
        self._status_bar.hint(
            buycoffee, lambda: "Buy the author a coffee on buycoffee.to, with BLIK or a Polish bank transfer."
        )

        ttk.Label(frame, text=LICENSE, foreground=DIM).grid(row=4, column=0, sticky="w", pady=(10, 0))

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
