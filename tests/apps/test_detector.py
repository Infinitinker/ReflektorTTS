from reflektortts.apps.detector import Builds, ProcessInfo, RunningApp, find_running_apps, running_processes
from reflektortts.apps.executable import ExecutableError
from reflektortts.profiles.model import App, Executable, Match, Profile

STEAM = "15e3cfedba9a841df67d8194e7249afb493b0e10d6138fb8ebab2c136e543efb"
RETAIL = "420af867036b1a66ef94c54b8db2e7e654da359031987c6602bcfa74972e089f"

GTA2 = Profile(id="gta2", app=App("Grand Theft Auto 2", 1999), match=Match((Executable("gta2.exe"),)))
OTHER = Profile(
    id="other",
    app=App("Other", 2001),
    match=Match((Executable("other.exe"), Executable("other64.exe"))),
)
SA = Profile(id="sa", app=App("San Andreas", 2004), match=Match((Executable("gta-sa.exe", (STEAM,)),)))


class Hashes:
    """Fake executables by process ID; counts how often each is hashed."""

    def __init__(self, by_pid: dict[int, str]) -> None:
        self.by_pid = by_pid
        self.hashed: list[int] = []

    def sha256(self, pid: int) -> str:
        self.hashed.append(pid)
        if pid not in self.by_pid:
            raise ExecutableError("Access is denied")
        return self.by_pid[pid]


def test_finds_games_by_process_name_ignoring_case() -> None:
    processes = [ProcessInfo(1, "explorer.exe"), ProcessInfo(2, "GTA2.EXE"), ProcessInfo(3, "other64.exe")]

    apps = find_running_apps([GTA2, OTHER], lambda: processes)

    assert apps == [
        RunningApp(GTA2, ProcessInfo(2, "GTA2.EXE")),
        RunningApp(OTHER, ProcessInfo(3, "other64.exe")),
    ]


def test_no_game_running_finds_nothing() -> None:
    assert find_running_apps([GTA2], lambda: [ProcessInfo(1, "explorer.exe")]) == []


def test_a_listed_build_is_supported_and_another_is_not() -> None:
    hashes = Hashes({1: STEAM, 2: RETAIL})
    builds = Builds(hashes.sha256)

    steam = find_running_apps([SA], lambda: [ProcessInfo(1, "gta-sa.exe")], builds)
    retail = find_running_apps([SA], lambda: [ProcessInfo(2, "gta-sa.exe")], builds)
    unreadable = find_running_apps([SA], lambda: [ProcessInfo(3, "gta-sa.exe")], builds)

    assert steam == [RunningApp(SA, ProcessInfo(1, "gta-sa.exe"), STEAM, supported=True)]
    assert retail == [RunningApp(SA, ProcessInfo(2, "gta-sa.exe"), RETAIL, supported=False)]
    assert unreadable == [RunningApp(SA, ProcessInfo(3, "gta-sa.exe"), None, supported=False)]


def test_each_process_is_hashed_once_and_only_where_builds_are_listed() -> None:
    hashes = Hashes({1: STEAM, 2: RETAIL})
    builds = Builds(hashes.sha256)
    processes = [ProcessInfo(1, "gta-sa.exe"), ProcessInfo(2, "gta2.exe")]

    for _ in range(3):
        find_running_apps([SA, GTA2], lambda: processes, builds)

    assert hashes.hashed == [1]


def test_running_processes_lists_this_process() -> None:
    import os

    assert any(process.pid == os.getpid() for process in running_processes())


def test_profiles_for_different_builds_of_one_executable_are_told_apart_by_build() -> None:
    retail = Profile(id="sa-retail", app=App("Retail", 2004), match=Match((Executable("gta-sa.exe", (RETAIL,)),)))
    builds = Builds(Hashes({1: RETAIL, 2: STEAM, 3: "0" * 64}).sha256)

    apps = find_running_apps(
        [SA, retail],
        lambda: [ProcessInfo(1, "gta-sa.exe"), ProcessInfo(2, "gta-sa.exe"), ProcessInfo(3, "gta-sa.exe")],
        builds,
    )

    assert [(app.profile.id, app.supported) for app in apps] == [("sa-retail", True), ("sa", True), ("sa", False)]
