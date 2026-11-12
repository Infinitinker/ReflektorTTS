"""Watching for apps: an app is read while it runs and its profile is in use, and an unsupported
build is shown until it exits."""

import threading

from reflektortts.apps.detector import ProcessInfo, RunningApp
from reflektortts.core.watching import Watcher
from reflektortts.events import ErrorEvent, Output, UnsupportedApp
from reflektortts.languages import Languages
from reflektortts.profiles.model import Profile
from tests.core.fake_plugins import SOURCES, STAGES, app_with


class FakeCore:
    """Uses the profiles it is given, and records what it is told about unsupported apps."""

    def __init__(self, *profiles: Profile) -> None:
        self.profiles = list(profiles)
        self.unsupported: list[tuple[UnsupportedApp | None, str | None]] = []

    def used_profiles(self) -> list[Profile]:
        return self.profiles

    def enter(self, app: RunningApp) -> None:
        raise NotImplementedError

    def leave(self) -> None:
        raise NotImplementedError

    def set_unsupported(self, unsupported: UnsupportedApp | None, profile_id: str | None) -> None:
        self.unsupported.append((unsupported, profile_id))

    def report(self, error: ErrorEvent) -> None:
        raise NotImplementedError

    def works_again(self, kind: str, origin: str) -> None:
        raise NotImplementedError

    def still_failing(self, error: ErrorEvent) -> None:
        raise NotImplementedError

    def stage_switch(self, key: str, output: Output) -> bool | None:
        return None

    def is_source_enabled(self, name: str) -> bool:
        return True

    def languages(self) -> Languages:
        return Languages("en", "en")


APP = app_with()


def watcher(core: FakeCore, running: set[int]) -> Watcher:
    return Watcher(core, SOURCES, STAGES, (), 47822, lambda pid: pid in running, lambda app, still_running: None)


def test_an_app_is_watched_while_it_runs_and_its_profile_is_used() -> None:
    core = FakeCore(APP.profile)
    running = {42}
    watching = watcher(core, running).watching(APP)

    assert watching(42)
    core.profiles = []
    assert not watching(42)
    core.profiles = [APP.profile]
    running.clear()
    assert not watching(42)


def test_an_unsupported_build_is_shown_until_it_exits_and_not_read() -> None:
    core = FakeCore(APP.profile)
    unsupported = RunningApp(APP.profile, ProcessInfo(7, "app.exe"), build="abc", supported=False)

    watcher(core, set()).wait_while_unsupported(unsupported, threading.Event())

    assert core.unsupported == [(UnsupportedApp("App", "abc"), "app"), (None, None)]
