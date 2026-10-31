"""The desktop app's window: what ReflektorTTS is doing, pause, and its folders."""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.status import CoreStatus, describe

PADDING = 16
WIDTH = 360
ICON_SIZES = (16, 32, 48, 256)
"""For the title bar, the taskbar and Alt+Tab; the system picks the size it needs."""


class Window:
    def __init__(
        self,
        root: tk.Tk,
        on_pause_toggle: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        self._root = root
        root.title("ReflektorTTS")
        # Kept here: Tkinter drops an image nothing in Python refers to.
        self._icons = [icon_photo(size) for size in ICON_SIZES]
        root.iconphoto(True, *self._icons)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", on_close)
        frame = ttk.Frame(root, padding=PADDING, width=WIDTH)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        self._status = ttk.Label(frame, text=describe(None))
        self._status.grid(row=0, column=0, columnspan=2, sticky="w")
        self._pause = ttk.Button(frame, text="Pause reading", command=on_pause_toggle, state="disabled")
        self._pause.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        hint = "In a game, open the ReflektorTTS panel with Ctrl+Shift+R."
        ttk.Label(frame, text=hint, wraplength=WIDTH).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 12))
        ttk.Button(frame, text="Open logs folder", command=on_open_logs).grid(row=3, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frame, text="Open settings folder", command=on_open_settings).grid(
            row=3, column=1, sticky="ew", padx=(4, 0)
        )

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
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def hide(self) -> None:
        self._root.withdraw()
