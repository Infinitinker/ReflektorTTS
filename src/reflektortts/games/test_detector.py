from reflektortts.games.detector import ProcessInfo, RunningGame, find_running_games, running_processes
from reflektortts.profiles.model import Game, Match, Profile

GTA2 = Profile(id="gta2", game=Game("Grand Theft Auto 2", 1999), match=Match(("gta2.exe",)))
OTHER = Profile(id="other", game=Game("Other", 2001), match=Match(("other.exe", "other64.exe")))


def test_finds_games_by_process_name_ignoring_case() -> None:
    processes = [ProcessInfo(1, "explorer.exe"), ProcessInfo(2, "GTA2.EXE"), ProcessInfo(3, "other64.exe")]

    games = find_running_games([GTA2, OTHER], lambda: processes)

    assert games == [
        RunningGame(GTA2, ProcessInfo(2, "GTA2.EXE")),
        RunningGame(OTHER, ProcessInfo(3, "other64.exe")),
    ]


def test_no_game_running_finds_nothing() -> None:
    assert find_running_games([GTA2], lambda: [ProcessInfo(1, "explorer.exe")]) == []


def test_running_processes_lists_this_process() -> None:
    import os

    assert any(process.pid == os.getpid() for process in running_processes())
