"""Ties the desktop app together: the core thread, the status feed, the tray icon and the window.

Tkinter works only on the thread that created it, so everything that touches the window runs
there: the status feed and the tray menu hand their work over through a queue.
"""

import json
import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from reflektortts.api.server import ApiError
from reflektortts.arguments import Arguments
from reflektortts.desktop.api_client import REFRESH_TIMEOUT_SECONDS, ApiClientError, StatusFeed, post, request_json
from reflektortts.desktop.catalog import DownloadItem, DownloadList, DownloadProgress, other_voices, parse_list
from reflektortts.desktop.core_thread import CoreThread
from reflektortts.desktop.folders import open_folder, show_file
from reflektortts.desktop.profiles import ProfileItem, file_name, name_text, parse_profiles
from reflektortts.desktop.status import CoreStatus, describe
from reflektortts.desktop.tray import Tray
from reflektortts.desktop.window import Window
from reflektortts.settings import SETTINGS_FOLDER
from reflektortts.user_dirs import config_dir, log_dir

logger = logging.getLogger(__name__)

POLL_MS = 100


class Application:
    def __init__(self, root: tk.Tk, args: Arguments) -> None:
        self._root = root
        self._tasks: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._status: CoreStatus | None = None
        self._stopped = False
        self._quitting = False
        """Set by quit: the window is gone, so nothing may touch it any more."""
        self._told_about_tray = False
        self._refreshed = False
        """Whether the download lists were fetched since the window was opened."""
        self._language_names: dict[str, str] = {}
        self._items: dict[str, DownloadItem] = {}
        self._core = CoreThread(args.profiles, config_dir(), args.overlay)
        self._feed = StatusFeed(
            lambda status: self._later(lambda: self._show(status)),
            lambda progress: self._later(lambda: self._download_progress(progress)),
            lambda preview: self._later(lambda: self._show_preview(preview.voice, preview.playing)),
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
            on_open_settings=lambda: open_folder(config_dir() / SETTINGS_FOLDER),
            on_close=self._hide,
            on_downloads_opened=self._downloads_opened,
            on_download=self._start_download,
            on_remove=self._remove_download,
            on_preview=self._preview,
            language_name=lambda code: self._language_names.get(code, code),
            on_profiles_opened=self._profiles_opened,
            on_enable_profile=self._enable_profile,
            on_copy_profile=self._copy_profile,
            on_remove_profile=self._remove_profile,
            on_import_profile=self._import_profile,
            on_reload_profiles=lambda: self._profile_request(
                "POST", "/profiles/reload", None, "The profiles could not be read again"
            ),
            on_open_profiles=lambda: open_folder(args.profiles),
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
        while not self._quitting and not self._tasks.empty():
            task = self._tasks.get()
            try:
                task()
            except Exception:
                # Tasks run from this timer, which must keep running: the tray's Quit comes through it.
                logger.exception("A window task failed")
        if self._quitting:
            return
        if not self._stopped and self._core.stopped():
            self._core_stopped()
        self._root.after(POLL_MS, self._run_tasks)

    def _show(self, status: CoreStatus | None) -> None:
        if self._stopped:
            return
        self._status = status
        # Whether profiles are read, disabled or unsupported changes with the status; the list
        # follows while it is shown.
        if status is not None and self._window.profiles_shown():
            self._in_background(self._fetch_profiles)
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
        message = "ReflektorTTS stopped: open the logs folder to see why."
        self._window.show_stopped(message)
        self._tray.show_status(message, paused=False, connected=False)

    def _toggle_pause(self) -> None:
        if self._status is None:
            return
        path = "/resume" if self._status.paused else "/pause"

        def toggle() -> None:
            try:
                post(path)
            except ApiClientError as error:
                logger.warning("%s", error)

        # In the background, like every request, so the window never waits for the core.
        self._in_background(toggle)

    def _profiles_opened(self) -> None:
        self._window.profiles.show_message("Loading…")
        self._in_background(self._fetch_profiles)

    def _fetch_profiles(self) -> None:
        """Runs in the background; the list is shown on Tkinter's thread."""
        try:
            items = parse_profiles(request_json("GET", "/profiles"))
        except ApiClientError as error:
            message = str(error)
            self._later(lambda: self._window.profiles.show_message(f"The profiles could not be loaded: {message}"))
            return
        self._later(lambda: self._window.profiles.show(items))

    def _enable_profile(self, item: ProfileItem, enabled: bool) -> None:
        action = "enabled" if enabled else "disabled"
        body = {"id": item.id, "enabled": enabled}
        self._profile_request("PATCH", "/profiles", body, f"{name_text(item)} could not be {action}")

    def _copy_profile(self, item: ProfileItem) -> None:
        """Copies a bundled profile and shows the copy, ready to edit."""

        def copy() -> None:
            try:
                answer = request_json("POST", f"/profiles/{item.id}/copy")
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_error(f"{name_text(item)} could not be copied: {message}"))
                return
            show_file(Path(answer["file"]))

        self._in_background(copy)

    def _remove_profile(self, item: ProfileItem) -> None:
        question = (
            f"Remove your own {file_name(item)}? The bundled profile is used again."
            if item.origin == "override"
            else f"Remove {file_name(item)}? The file is deleted."
        )
        if messagebox.askyesno("ReflektorTTS", question, parent=self._root):
            self._profile_request("DELETE", f"/profiles/{item.id}", None, f"{file_name(item)} could not be removed")

    def _import_profile(self, replace: bool = False, chosen: str = "") -> None:
        """Asks for a profile file and sends its contents; the core checks it before saving it."""
        path = chosen or filedialog.askopenfilename(
            parent=self._root, title="Import a profile", filetypes=[("Profiles", "*.json"), ("All files", "*")]
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text("utf-8-sig"))
        except (OSError, ValueError) as error:
            self._show_error(f"{Path(path).name} cannot be read as a profile: {error}")
            return
        body = {"id": Path(path).stem, "profile": data, "replace": replace}

        def send() -> None:
            try:
                request_json("POST", "/profiles", body)
            except ApiClientError as error:
                message = str(error)
                if error.status == 409:
                    self._later(lambda: self._confirm_replace(message, path))
                else:
                    self._later(lambda: self._show_error(f"{Path(path).name} was not imported: {message}"))

        self._in_background(send)

    def _confirm_replace(self, message: str, path: str) -> None:
        if messagebox.askyesno("ReflektorTTS", f"{message} Replace it?", parent=self._root):
            self._import_profile(replace=True, chosen=path)

    def _profile_request(self, method: str, path: str, body: Any, failure: str) -> None:
        """Sends a change to the profiles in the background; the status event that follows
        refreshes the list."""

        def send() -> None:
            try:
                request_json(method, path, body)
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_error(f"{failure}: {message}"))

        self._in_background(send)

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
            downloads = parse_list(request_json("GET", path, timeout=timeout))
            others = other_voices(request_json("GET", "/voices"), downloads.items, self._language_names)
        except ApiClientError as error:
            message = str(error)
            self._later(lambda: self._list_failed(message))
            return
        listing = DownloadList((*downloads.items, *others), downloads.errors)
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

    def _preview(self, item: DownloadItem) -> None:
        def preview() -> None:
            try:
                request_json("POST", "/voices/preview", {"voice": item.id})
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_preview(item.id, False))
                self._later(lambda: self._show_error(f"{item.name} could not be previewed: {message}"))

        self._in_background(preview)

    def _show_preview(self, voice: str, playing: bool) -> None:
        for tab in self._window.downloads.values():
            tab.show_preview(voice, playing)

    def _in_background(self, work: Callable[[], None]) -> None:
        threading.Thread(target=work, name="api request", daemon=True).start()

    def _window_show(self) -> None:
        self._window.show()

    def _hide(self) -> None:
        self._window.hide()
        self._refreshed = False
        if not self._told_about_tray:
            self._told_about_tray = True
            self._tray.notify(
                "Still running", "ReflektorTTS keeps reading apps from here. Right-click its icon to quit."
            )

    def _quit(self) -> None:
        self._quitting = True
        self._window.hide()
        self._tray.stop()
        self._feed.stop()
        if not self._core.stopped():
            self._core.stop()
        self._root.destroy()
