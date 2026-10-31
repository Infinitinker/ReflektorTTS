"""Ties the desktop app together: the core thread, the status feed, the tray icon and the window.

Tkinter works only on the thread that created it, so everything that touches the window runs
there: the status feed and the tray menu hand their work over through a queue.
"""

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

from reflektortts.api.server import ApiError
from reflektortts.app import NoProfilesError
from reflektortts.arguments import Arguments
from reflektortts.desktop.api_client import ApiClientError, StatusFeed, post
from reflektortts.desktop.core_thread import CoreThread
from reflektortts.desktop.folders import open_folder
from reflektortts.desktop.status import CoreStatus, describe
from reflektortts.desktop.tray import Tray
from reflektortts.desktop.window import Window
from reflektortts.user_dirs import config_dir, log_dir

logger = logging.getLogger(__name__)

POLL_MS = 100


class Application:
    def __init__(self, root: tk.Tk, args: Arguments) -> None:
        self._root = root
        self._tasks: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._status: CoreStatus | None = None
        self._stopped = False
        self._told_about_tray = False
        self._core = CoreThread(args.profiles, config_dir(), args.overlay)
        self._feed = StatusFeed(lambda status: self._later(lambda: self._show(status)))
        self._tray = Tray(
            on_open=lambda: self._later(self._window_show),
            on_pause_toggle=lambda: self._later(self._toggle_pause),
            on_quit=lambda: self._later(self._quit),
        )
        self._window = Window(
            root,
            on_pause_toggle=self._toggle_pause,
            on_open_logs=lambda: open_folder(log_dir()),
            on_open_settings=lambda: open_folder(config_dir()),
            on_close=self._hide,
        )

    def start(self) -> None:
        self._core.start()
        self._feed.start()
        self._tray.start()
        self._root.after(POLL_MS, self._run_tasks)

    def _later(self, task: Callable[[], None]) -> None:
        """Runs task on Tkinter's thread; safe to call from any thread."""
        self._tasks.put(task)

    def _run_tasks(self) -> None:
        while not self._tasks.empty():
            self._tasks.get()()
        if not self._stopped and self._core.stopped():
            self._core_stopped()
        self._root.after(POLL_MS, self._run_tasks)

    def _show(self, status: CoreStatus | None) -> None:
        if self._stopped:
            return
        self._status = status
        self._window.show_status(status)
        self._tray.show_status(describe(status), status is not None and status.paused, status is not None)

    def _core_stopped(self) -> None:
        self._stopped = True
        error = self._core.error
        if isinstance(error, ApiError):
            messagebox.showerror(
                "ReflektorTTS", "ReflektorTTS is already running: look for its icon next to the clock."
            )
            self._quit()
            return
        if isinstance(error, NoProfilesError):
            messagebox.showerror("ReflektorTTS", str(error))
        message = "ReflektorTTS stopped: open the logs folder to see why."
        self._window.show_stopped(message)
        self._tray.show_status(message, paused=False, connected=False)

    def _toggle_pause(self) -> None:
        if self._status is None:
            return
        try:
            post("/resume" if self._status.paused else "/pause")
        except ApiClientError as error:
            logger.warning("%s", error)

    def _window_show(self) -> None:
        self._window.show()

    def _hide(self) -> None:
        self._window.hide()
        if not self._told_about_tray:
            self._told_about_tray = True
            self._tray.notify("ReflektorTTS keeps running here. Right-click its icon to quit.")

    def _quit(self) -> None:
        self._window.hide()
        self._tray.stop()
        self._feed.stop()
        if not self._core.stopped():
            self._core.stop()
        self._root.destroy()
