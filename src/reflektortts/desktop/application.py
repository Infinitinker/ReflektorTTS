"""Ties the desktop app together: the core thread, the status feed, the tray icon and the window.

Tkinter works only on the thread that created it, so everything that touches the window runs
there: the status feed and the tray menu hand their work over through a queue.
"""

import json
import logging
import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from reflektortts.api.server import ApiError
from reflektortts.arguments import Arguments
from reflektortts.desktop.about import about
from reflektortts.desktop.api.catalog import DownloadItem, DownloadList, DownloadProgress, other_voices, parse_list
from reflektortts.desktop.api.client import (
    REFRESH_TIMEOUT_SECONDS,
    ApiClientError,
    StatusFeed,
    post,
    reflektortts_answers,
    request_json,
)
from reflektortts.desktop.api.integrations import IntegrationItem, failure_text, parse_integrations
from reflektortts.desktop.api.profiles import ProfileItem, file_name, name_text, parse_profiles
from reflektortts.desktop.api.status import CoreStatus, describe
from reflektortts.desktop.core_thread import CoreThread
from reflektortts.desktop.panel.dock import dock_of
from reflektortts.desktop.panel.launcher import PanelWindows, find_program
from reflektortts.desktop.system.autostart import autostart_supported, system_autostart
from reflektortts.desktop.system.folders import open_folder, show_file, where_files_are
from reflektortts.desktop.system.session import quit_on_sign_out
from reflektortts.desktop.system.state import load_state, save_state
from reflektortts.desktop.system.tray_host import tray_available
from reflektortts.desktop.tray import Tray
from reflektortts.desktop.window import Window
from reflektortts.identity import api_port, app_name
from reflektortts.settings import SETTINGS_FOLDER
from reflektortts.user_dirs import config_dir, log_dir, state_dir

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
        self._state = load_state(state_dir())
        self._autostart = system_autostart()
        self._has_tray = tray_available()
        """Without a tray there is no icon to open the window from again, so the window is never hidden."""
        self._hidden = args.hidden and self._has_tray
        self._refreshed = False
        """Whether the download lists were fetched since the window was opened."""
        self._language_names: dict[str, str] = {}
        self._voice_titles: dict[str, str] = {}
        """Voices by their ID, e.g. "Microsoft Adam (Windows)", as the core lists them."""
        self._fetching_names = False
        self._names_for: str | None = None
        """The voice the names were last fetched for, so a voice the core does not list is asked about once."""
        self._items: dict[str, DownloadItem] = {}
        self._core = CoreThread(args.profiles, config_dir(), args.overlay)
        self._panels = PanelWindows(find_program(args.overlay), api_port())
        """The settings windows, one per profile, opened from the Profiles tab or, for the app being
        read, the Status tab."""
        self._feed = StatusFeed(
            lambda status: self._later(lambda: self._show(status)),
            lambda progress: self._later(lambda: self._download_progress(progress)),
            lambda preview: self._later(lambda: self._show_preview(preview.voice, preview.playing)),
        )
        self._tray = Tray(
            on_open=lambda: self._later(self._window_show),
            on_pause_toggle=lambda: self._later(self._toggle_pause),
            on_quit=lambda: self._later(self._quit),
            start_with_windows=self._start_with_windows,
            on_start_with_windows_toggle=lambda: self._later(
                lambda: self._set_start_with_windows(not self._start_with_windows())
            ),
        )
        self._window = Window(
            root,
            on_pause_toggle=self._toggle_pause,
            on_open_logs=lambda: open_folder(log_dir()),
            on_open_settings=lambda: open_folder(config_dir() / SETTINGS_FOLDER),
            on_close=self._close,
            on_downloads_opened=self._downloads_opened,
            on_download=self._start_download,
            on_remove=self._remove_download,
            on_preview=self._preview,
            language_name=lambda code: self._language_names.get(code, code),
            voice_title=lambda voice: self._voice_titles.get(voice, voice),
            on_profiles_opened=self._profiles_opened,
            on_enable_profile=self._enable_profile,
            on_app_settings=lambda item: self._open_app_settings(item.id, name_text(item)),
            on_read_app_settings=self._open_app_settings,
            app_settings_missing=self._panels.missing,
            on_copy_profile=self._copy_profile,
            on_remove_profile=self._remove_profile,
            on_import_profile=self._import_profile,
            on_reload_profiles=lambda: self._profile_request(
                "POST", "/profiles/reload", None, "The profiles could not be read again"
            ),
            on_open_profiles=lambda: open_folder(args.profiles),
            on_integration=self._change_integration,
            on_start_with_windows=self._set_start_with_windows,
            on_quit=self._quit,
            on_open_link=self._open_link,
            about=about(),
            files_text=where_files_are(),
            autostart_supported=autostart_supported(),
            has_tray=self._has_tray,
        )
        self._window.settings.show_start_with_windows(self._start_with_windows())

    def start(self) -> None:
        quit_on_sign_out(self._root, self._quit)
        self._core.start()
        self._feed.start()
        if self._has_tray:
            self._tray.start()
        self._root.after(POLL_MS, self._run_tasks)
        if self._hidden:
            self._window.hide()

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
        if status is not None and status.voice != self._names_for and not self._fetching_names:
            # The status names its voice and languages by ID; the core knows their names.
            self._names_for = status.voice
            self._fetching_names = True
            self._in_background(self._fetch_names)
        self._window.status.show(status)
        self._tray.show_status(describe(status), status is not None and status.paused, status is not None)

    def _fetch_names(self) -> None:
        """Runs in the background; the status is shown again with the names on Tkinter's thread."""
        try:
            languages = request_json("GET", "/languages")["languages"]
            names = {language["code"]: language["english_name"] for language in languages}
            voices = request_json("GET", "/voices")["voices"]
            titles = {voice["id"]: f"{voice['name']} ({voice['engine_title']})" for voice in voices}
        except (ApiClientError, KeyError, TypeError) as error:
            logger.warning("Cannot get the names of the voices and languages: %s", error)
            self._later(self._names_failed)
            return

        def show() -> None:
            self._fetching_names = False
            self._language_names = names
            self._voice_titles = titles
            if not self._stopped:
                self._window.status.show(self._status)

        self._later(show)

    def _names_failed(self) -> None:
        """The next status tries again."""
        self._fetching_names = False
        self._names_for = None

    def _core_stopped(self) -> None:
        self._stopped = True
        error = self._core.error
        if isinstance(error, ApiError):
            # Whatever holds the port may not be ReflektorTTS; asking it takes a moment.
            self._in_background(self._check_port)
            return
        message = "Stopped: open the logs folder, in the Settings tab, to see why."
        self._window.status.show_stopped(message)
        self._tray.show_status(message, paused=False, connected=False)

    def _check_port(self) -> None:
        """Runs in the background: asks whatever holds the port, then hands the answer to Tkinter."""
        by_reflektortts = reflektortts_answers()
        self._later(lambda: self._port_taken(by_reflektortts))

    def _port_taken(self, by_reflektortts: bool) -> None:
        """The local API could not open its port: tells the user why, then quits."""
        if by_reflektortts:
            message = f"{app_name()} is already running: look for its icon next to the clock."
        else:
            message = (
                f"{app_name()} cannot start: port {api_port()} on this computer is used by another program, "
                "or reserved by the system. Close the other program, or restart the computer, and start "
                "ReflektorTTS again."
            )
        messagebox.showerror("ReflektorTTS", message)
        self._quit()

    def _toggle_pause(self) -> None:
        if self._status is None:
            return
        path = "/resume" if self._status.paused else "/pause"
        action = "resumed" if self._status.paused else "paused"

        def toggle() -> None:
            try:
                post(path)
            except ApiClientError as error:
                message = str(error)
                self._later(lambda: self._show_error(f"ReflektorTTS could not be {action}: {message}"))

        # In the background, like every request, so the window never waits for the core.
        self._in_background(toggle)

    def _profiles_opened(self) -> None:
        self._window.profiles.show_message("Loading…")
        self._in_background(self._fetch_profiles)

    def _fetch_profiles(self) -> None:
        """Runs in the background; the list is shown on Tkinter's thread, with the integrations."""
        try:
            items = parse_profiles(request_json("GET", "/profiles"))
            integrations = parse_integrations(request_json("GET", "/integrations"))
        except ApiClientError as error:
            message = str(error)
            self._later(lambda: self._window.profiles.show_message(f"The profiles could not be loaded: {message}"))
            return
        self._later(lambda: self._window.profiles.show(items, integrations))

    def _change_integration(self, item: IntegrationItem, enabled: bool) -> None:
        body = {"enabled": enabled}
        self._profile_request("PATCH", f"/integrations/{item.id}", body, failure_text(item, enabled))

    def _enable_profile(self, item: ProfileItem, enabled: bool) -> None:
        action = "enabled" if enabled else "disabled"
        body = {"id": item.id, "enabled": enabled}
        self._profile_request("PATCH", "/profiles", body, f"{name_text(item)} could not be {action}")

    def _open_app_settings(self, profile: str, title: str) -> None:
        """Opens the profile's settings window beside this one, or brings it to the front; it talks to
        the core itself. title names the app in an error."""
        try:
            self._panels.open(profile, lambda: dock_of(self._root))
        except OSError:
            logger.exception("Cannot open the settings window for %s", profile)
            self._show_error(
                f"The settings window for {title} could not be opened: try again, and if it still does not "
                "open, install or unpack ReflektorTTS again."
            )

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
        name = Path(path).name
        try:
            data = json.loads(Path(path).read_text("utf-8-sig"))
        except OSError as error:
            logger.warning("Cannot open %s: %s", path, error)
            self._show_error(f"{name} could not be opened: check that the file is still there, then try again.")
            return
        except ValueError as error:
            logger.warning("Cannot read %s as a profile: %s", path, error)
            self._show_error(f"{name} cannot be read as a profile: choose a profile file, written in JSON.")
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
                self._language_names = {language["code"]: language["english_name"] for language in languages}
            if refresh:
                answer = request_json("POST", "/downloads/refresh", timeout=REFRESH_TIMEOUT_SECONDS)
            else:
                answer = request_json("GET", "/downloads")
            downloads = parse_list(answer)
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
        # Over a window that holds the grab (the integration window), so it is the one blocked.
        grabbing = self._root.grab_current()  # type: ignore[no-untyped-call]  # Untyped in typeshed.
        messagebox.showerror("ReflektorTTS", message, parent=grabbing or self._root)

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
        # Task Manager may have changed it meanwhile.
        self._window.settings.show_start_with_windows(self._start_with_windows())
        self._tray.refresh()
        self._window.show()

    def _close(self) -> None:
        """Closing the window hides it, and the tray icon opens it again; with no tray, it quits."""
        if self._has_tray:
            self._hide()
        else:
            self._quit()

    def _hide(self) -> None:
        self._window.hide()
        self._refreshed = False
        if self._tray.can_notify and not self._state.told_about_tray:
            self._state = replace(self._state, told_about_tray=True)
            try:
                save_state(self._state, state_dir())
            except OSError as error:
                logger.warning("Cannot remember that the tray notice was shown: %s", error)
            self._tray.notify("Still running", "Keeps reading apps from here. Right-click the icon to quit.")

    def _open_link(self, url: str) -> None:
        """Opens a web page in the user's browser."""
        if not webbrowser.open(url):
            logger.warning("No web browser could open %s", url)
            self._show_error(f"No web browser could be opened. The page is {url}")

    def _start_with_windows(self) -> bool | None:
        """Whether ReflektorTTS starts with Windows; None where it cannot. Called on any thread."""
        return None if self._autostart is None else self._autostart.enabled()

    def _set_start_with_windows(self, enabled: bool) -> None:
        if self._autostart is None:
            return
        try:
            self._autostart.enable(enabled)
        except OSError:
            logger.exception("Cannot change whether ReflektorTTS starts with Windows")
            self._show_error(
                "Start with Windows could not be changed: try again, or turn it on or off in Windows "
                "Settings > Apps > Startup."
            )
        self._window.settings.show_start_with_windows(self._start_with_windows())
        self._tray.refresh()

    def _quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._window.hide()
        self._tray.stop()
        self._panels.close_all()
        self._feed.stop()
        if not self._core.stopped():
            self._core.stop()
        self._root.destroy()
