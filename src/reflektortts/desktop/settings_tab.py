"""The window's Settings tab: settings of ReflektorTTS itself, not of the apps it reads (those are set
in the overlay's panel): whether it starts with Windows, and where its files are."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.status_bar import StatusBar
from reflektortts.desktop.theme import DIM

PADDING = 16


class SettingsTab:
    def __init__(
        self,
        notebook: ttk.Notebook,
        status_bar: StatusBar,
        files_text: str,
        autostart_supported: bool,
        on_start_with_windows: Callable[[bool], None],
        on_open_settings: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_profiles: Callable[[], None],
    ) -> None:
        self.frame = ttk.Frame(notebook, padding=PADDING)
        self.frame.columnconfigure(0, weight=1)
        row = 0

        self._start_with_windows = tk.BooleanVar(value=False)
        self._available = False
        self._autostart: ttk.Checkbutton | None = None
        if autostart_supported:
            startup = ttk.LabelFrame(self.frame, text="Startup", padding=12)
            startup.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            row += 1
            self._autostart = ttk.Checkbutton(
                startup,
                text="Start with Windows",
                variable=self._start_with_windows,
                command=lambda: on_start_with_windows(self._start_with_windows.get()),
                state="disabled",
            )
            self._autostart.grid(row=0, column=0, sticky="w")
            ttk.Label(
                startup,
                text="ReflektorTTS starts hidden next to the clock when you sign in, ready to read your apps.",
                foreground=DIM,
            ).grid(row=1, column=0, sticky="w", padx=(22, 0))
            status_bar.hint(self._autostart, self._autostart_hint)

        files = ttk.LabelFrame(self.frame, text="Your files", padding=12)
        files.grid(row=row, column=0, sticky="ew")
        ttk.Label(
            files,
            text=files_text,
            foreground=DIM,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        buttons = ttk.Frame(files)
        buttons.grid(row=1, column=0, sticky="w")
        settings = ttk.Button(buttons, text="Open settings folder", command=on_open_settings)
        settings.grid(row=0, column=0)
        logs = ttk.Button(buttons, text="Open logs folder", command=on_open_logs)
        logs.grid(row=0, column=1, padx=(6, 0))
        profiles = ttk.Button(buttons, text="Open profiles folder", command=on_open_profiles)
        profiles.grid(row=0, column=2, padx=(6, 0))
        status_bar.hint(settings, lambda: "Open the folder with the settings saved for each app.")
        status_bar.hint(logs, lambda: "Open the folder with ReflektorTTS's logs, e.g. to report a problem.")
        status_bar.hint(profiles, lambda: "Open the folder for your own profiles, which the Profiles tab lists too.")

    def show_start_with_windows(self, enabled: bool | None) -> None:
        """Whether ReflektorTTS starts with Windows; None where it cannot."""
        self._available = enabled is not None
        self._start_with_windows.set(bool(enabled))
        if self._autostart is not None:
            self._autostart.configure(state="normal" if self._available else "disabled")

    def _autostart_hint(self) -> str:
        if self._available:
            return "Start ReflektorTTS, hidden next to the clock, when you sign in to Windows."
        return "Only ReflektorTTS.exe from a release can start with Windows."
