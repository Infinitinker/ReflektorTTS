"""Finds running apps, and other programs with a profile, by their executable's name and, where
the profile lists builds, its SHA-256."""

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import psutil

from reflektortts.apps.executable import ExecutableError, executable_sha256
from reflektortts.profiles.model import Executable, Profile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str


@dataclass(frozen=True)
class RunningApp:
    profile: Profile
    process: ProcessInfo
    build: str | None = None
    """The executable's SHA-256, if the profile lists builds and it could be read."""
    supported: bool = True
    """False for a build the profile does not list: it is neither read nor given the overlay."""


def running_processes() -> list[ProcessInfo]:
    return [
        ProcessInfo(pid=process.info["pid"], name=process.info["name"])
        for process in psutil.process_iter(["pid", "name"])
        if process.info["name"]
    ]


class Builds:
    """Identifies builds, hashing each process's executable once: a big executable takes a moment
    to hash, and the detector looks every few seconds."""

    def __init__(self, sha256: Callable[[int], str] = executable_sha256) -> None:
        self._sha256 = sha256
        self._known: dict[ProcessInfo, str | None] = {}

    def of(self, process: ProcessInfo) -> str | None:
        """The SHA-256 of the process's executable, or None if it cannot be read."""
        if process not in self._known:
            try:
                self._known[process] = self._sha256(process.pid)
            except ExecutableError as error:
                logger.warning("Cannot identify %s: %s", process.name, error)
                self._known[process] = None
        return self._known[process]


def find_running_apps(
    profiles: Sequence[Profile],
    list_processes: Callable[[], Iterable[ProcessInfo]] = running_processes,
    builds: Builds | None = None,
) -> list[RunningApp]:
    """Returns every running process that a profile's executables name, in process order; a
    build no profile lists is returned as not supported.

    Several profiles can name one executable when they list different builds of it (e.g. a
    retail and a Steam release); the build decides. Names are compared case-insensitively, since
    Windows ignores case in file names.
    """
    builds = builds or Builds()
    by_name: dict[str, list[tuple[Profile, Executable]]] = {}
    for profile in profiles:
        for executable in profile.match.executables:
            by_name.setdefault(executable.name.lower(), []).append((profile, executable))
    apps = []
    for process in list_processes():
        candidates = by_name.get(process.name.lower())
        if not candidates:
            continue
        any_build = next((profile for profile, executable in candidates if not executable.sha256), None)
        if any_build is not None:
            apps.append(RunningApp(any_build, process))
            continue
        build = builds.of(process)
        listing = next((profile for profile, executable in candidates if build in executable.sha256), None)
        if listing is not None:
            apps.append(RunningApp(listing, process, build))
        else:
            apps.append(RunningApp(candidates[0][0], process, build, supported=False))
    return apps
