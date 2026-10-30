"""Finds running games by matching process names against profiles."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import psutil

from reflektortts.profiles.model import Profile


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str


@dataclass(frozen=True)
class RunningGame:
    profile: Profile
    process: ProcessInfo


def running_processes() -> list[ProcessInfo]:
    return [
        ProcessInfo(pid=process.info["pid"], name=process.info["name"])
        for process in psutil.process_iter(["pid", "name"])
        if process.info["name"]
    ]


def find_running_games(
    profiles: Sequence[Profile],
    list_processes: Callable[[], Iterable[ProcessInfo]] = running_processes,
) -> list[RunningGame]:
    """Returns every running process that a profile's match.process names, in process order.

    Names are compared case-insensitively, since Windows ignores case in file names.
    """
    by_name = {name.lower(): profile for profile in profiles for name in profile.match.processes}
    return [
        RunningGame(profile=by_name[process.name.lower()], process=process)
        for process in list_processes()
        if process.name.lower() in by_name
    ]
