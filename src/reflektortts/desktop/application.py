"""Ties the desktop app together: the core thread, the status feed, the tray icon and the window.

Tkinter works only on the thread that created it, so everything that touches the window runs
there: the status feed and the tray menu hand their work over through a queue.
"""

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

from reflektortts.api.server import ApiError
from reflektortts.app import NoProfilesError
from reflektortts.arguments import Arguments
from reflektortts.desktop.api_client import REFRESH_TIMEOUT_SECONDS, ApiClientError, StatusFeed, post, request_json
from reflektortts.desktop.catalog import DownloadItem, DownloadList, DownloadProgress, parse_list
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
        self._refreshed = False
        """Whether the download lists were fetched since the window was opened."""
        self._language_names: dict[str, str] = {}
        self._items: dict[str, DownloadItem] = {}
        self._core = CoreThread(args.profiles, config_dir(), args.overlay)
        self._feed = StatusFeed(
            lambda status: self._later(lambda: self._show(status)),
            lambda progress: self._later(lambda: self._download_progress(progress)),
        )
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
            on_downloads_opened=self._downloads_opened,
            on_download=self._start_download,
            on_remove=self._remove_download,
            language_name=lambda code: self._language_names.get(code, code),
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

    def _downloads_opened(self) -> None:
        """A downloads tab was opened: the lists are fetched from the internet once per opening
        of the window, in the background."""
        if self._refreshed:
            return
        self._refreshed = True
        for tab in self._window.downloads.values():
            tab.show_message("Loading…")
        self._in_background(lambda: self._fetch_list(refresh=True))

    def _fetch_list(self, refresh: bool) -> None:
        """Runs in the background; the list is shown on Tkinter's thread. Errors are reported
        when the list is fetched from the internet, not each time it is shown again."""
        try:
            if not self._language_names:
                languages = request_json("GET", "/languages")["languages"]
                self._language_names = {language["code"]: language["name"] for language in languages}
            path = "/downloads?refresh=1" if refresh else "/downloads"
            timeout = REFRESH_TIMEOUT_SECONDS if refresh else 5.0
            listing = parse_list(request_json("GET", path, timeout=timeout))
        except ApiClientError as error:
            message = str(error)
            self._later(lambda: self._list_failed(message))
            return
        self._later(lambda: self._show_list(listing, report_errors=refresh))

    def _show_list(self, listing: DownloadList, report_errors: bool) -> None:
        self._items = {item.id: item for item in listing.items}
        for kind, tab in self._window.downloads.items():
            tab.show([item for item in listing.items if item.kind == kind])
        if report_errors and listing.errors:
            self._show_error("\n\n".join(listing.errors))

    def _list_failed(self, message: str) -> None:
        for tab in self._window.downloads.values():
            tab.show_message("The list could not be loaded. Close and open the window to try again.")
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("ReflektorTTS", message, parent=self._root)

    def _start_download(self, item: DownloadItem) -> None:
        def start() -> None:
            try:
                request_json("POST", "/downloads", {"id": item.id})
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_error(f"{item.name} could not be downloaded: {message}"))
                self._fetch_list(refresh=False)

        self._in_background(start)

    def _remove_download(self, item: DownloadItem) -> None:
        if not messagebox.askyesno("ReflektorTTS", f"Remove {item.name}? You can download it again later."):
            return

        def remove() -> None:
            try:
                request_json("DELETE", f"/downloads/{item.id}")
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_error(f"{item.name} could not be removed: {message}"))

        self._in_background(remove)

    def _download_progress(self, progress: DownloadProgress) -> None:
        for tab in self._window.downloads.values():
            tab.show_progress(progress)
        item = self._items.get(progress.id)
        if progress.state in ("installed", "removed", "failed"):
            self._in_background(lambda: self._fetch_list(refresh=False))
        if progress.state == "failed" and item is not None:
            self._show_error(f"{item.name} could not be downloaded: {progress.message}")

    def _in_background(self, work: Callable[[], None]) -> None:
        threading.Thread(target=work, name="api request", daemon=True).start()

    def _window_show(self) -> None:
        self._window.show()

    def _hide(self) -> None:
        self._window.hide()
        self._refreshed = False
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
