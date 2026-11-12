"""Watching for the apps of the profiles in use, and reading each that starts, one at a time, until
it exits or its profile is set aside."""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from reflektortts.apps.detector import Builds, ProcessInfo, RunningApp, find_running_apps
from reflektortts.core.reading import APP_CHECK_SECONDS, build_routes, read_app
from reflektortts.events import ErrorEvent, Output, UnsupportedApp
from reflektortts.languages import Languages
from reflektortts.overlay import inject_overlay
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.protocols import Sink
from reflektortts.profiles.model import Profile

logger = logging.getLogger(__name__)


class WatchedCore(Protocol):
    """What the watcher tells the core, and asks it, about the apps it reads."""

    def used_profiles(self) -> list[Profile]:
        """The profiles whose apps are to be read."""
        ...

    def enter(self, app: RunningApp) -> None:
        """An app is read from now on."""
        ...

    def leave(self) -> None:
        """The app is no longer read."""
        ...

    def set_unsupported(self, unsupported: UnsupportedApp | None, profile_id: str | None) -> None:
        """An app runs in a version its profile does not support, or none does any more."""
        ...

    def report(self, error: ErrorEvent) -> None: ...

    def works_again(self, kind: str, origin: str) -> None: ...

    def still_failing(self, error: ErrorEvent) -> None: ...

    def stage_switch(self, key: str, output: Output) -> bool | None: ...

    def is_source_enabled(self, name: str) -> bool: ...

    def languages(self) -> Languages: ...


class Watcher:
    """Finds the running apps of the core's profiles and reads them; see run."""

    def __init__(
        self,
        core: WatchedCore,
        sources: Mapping[str, SourcePlugin],
        stages: Mapping[str, StagePlugin],
        overlay_dirs: Sequence[Path],
        is_running: Callable[[int], bool],
        watch_sound: Callable[[ProcessInfo | None, bool], None],
    ) -> None:
        """watch_sound is given the app whose sound to lower while it is read, or None, and
        whether the app left still runs (see Ducker.watch)."""
        self._core = core
        self._sources = sources
        self._stages = stages
        self._overlay_dirs = overlay_dirs
        self._is_running = is_running
        self._watch_sound = watch_sound
        self._builds = Builds()

    def run(self, stop: threading.Event, sinks: Mapping[Output, Sequence[Sink]]) -> None:
        """Reads every app of the profiles in use that starts, one at a time, until stop is set."""
        core = self._core
        while not stop.is_set():
            apps = sorted(
                find_running_apps(core.used_profiles(), builds=self._builds), key=lambda app: not app.supported
            )
            if not apps:
                stop.wait(APP_CHECK_SECONDS)
                continue
            app = apps[0]
            if not app.supported:
                self.wait_while_unsupported(app, stop)
                continue
            core.enter(app)
            self._watch_sound(app.process, False)
            if app.profile.overlay and self._overlay_dirs:
                inject_overlay(app.process.pid, self._overlay_dirs)
            routes = build_routes(
                app,
                self._sources,
                self._stages,
                core.report,
                core.stage_switch,
                core.is_source_enabled,
                core.languages,
            )
            if routes:
                logger.info("Reading %s aloud", app.profile.app.title)
            elif not app.profile.sources:
                logger.warning("%s is running, but its profile has no sources to read yet.", app.profile.app.title)
            else:
                logger.error("%s is running, but none of its sources could start.", app.profile.app.title)
            read_app(
                app,
                routes,
                sinks,
                stop,
                core.report,
                self.watching(app),
                languages=core.languages,
                on_works_again=core.works_again,
                on_still_failing=core.still_failing,
            )
            still_running = self._is_running(app.process.pid)
            logger.info("Stopped reading %s" if still_running else "%s closed", app.profile.app.title)
            self._watch_sound(None, still_running)
            core.leave()

    def wait_while_unsupported(self, app: RunningApp, stop: threading.Event) -> None:
        """A build the profile does not list is neither read nor given the overlay; the user is
        told, until it exits."""
        title = app.profile.app.title
        logger.warning(
            "%s is running, but this version of it is not supported yet (%s has SHA-256 %s)",
            title,
            app.process.name,
            app.build or "unknown",
        )
        self._core.set_unsupported(UnsupportedApp(title, app.build), app.profile.id)
        watching = self.watching(app)
        while not stop.is_set() and watching(app.process.pid):
            stop.wait(APP_CHECK_SECONDS)
        self._core.set_unsupported(None, None)

    def watching(self, app: RunningApp) -> Callable[[int], bool]:
        """Whether an app is still to be read: it runs, and its profile was not disabled (or
        set aside) meanwhile, which ends reading as if the app had closed."""

        def watching(pid: int) -> bool:
            return self._is_running(pid) and any(profile.id == app.profile.id for profile in self._core.used_profiles())

        return watching
