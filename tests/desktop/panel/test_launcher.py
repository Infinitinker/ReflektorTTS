import sys
from pathlib import Path

import pytest

from reflektortts.desktop.panel.dock import Dock
from reflektortts.desktop.panel.launcher import PROGRAM, PanelWindows, find_program


class FakeProcess:
    def __init__(self, command: list[str], pid: int) -> None:
        self.command = command
        self.pid = pid
        self.exit_code: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = 1


class FakeLauncher:
    def __init__(self) -> None:
        self.started: list[FakeProcess] = []

    def __call__(self, command: list[str]) -> FakeProcess:
        process = FakeProcess(command, pid=1000 + len(self.started))
        self.started.append(process)
        return process


class FakeFronter:
    def __init__(self) -> None:
        self.brought: list[int] = []

    def __call__(self, pid: int) -> bool:
        self.brought.append(pid)
        return True


def program_in(folder: Path) -> Path:
    folder.mkdir(parents=True)
    program = folder / PROGRAM
    program.write_bytes(b"")
    return program


def test_run_from_source_the_first_overlay_folder_with_the_program_has_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    x86 = tmp_path / "build" / "bin"
    x86.mkdir(parents=True)
    program = program_in(tmp_path / "build64" / "bin")

    assert find_program([x86, program.parent]) == program
    assert find_program([x86]) is None


def test_in_a_release_the_program_is_in_the_panel_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    program = program_in(tmp_path / "ReflektorTTS" / "panel")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ReflektorTTS" / "reflektortts.exe"))
    overlay = program_in(tmp_path / "ReflektorTTS" / "overlay" / "x64")

    assert find_program([overlay.parent]) == program


def test_in_a_release_a_program_next_to_the_exe_is_not_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    program_in(tmp_path / "ReflektorTTS")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ReflektorTTS" / "reflektortts.exe"))

    assert find_program([]) is None


def test_in_a_release_without_the_program_there_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "reflektortts.exe"))

    assert find_program([]) is None
    assert PanelWindows(None).missing is not None


def test_opening_starts_the_program_for_the_profile() -> None:
    launcher = FakeLauncher()
    panels = PanelWindows(Path("panel"), launcher, FakeFronter())

    assert panels.missing is None
    panels.open("gta2")

    assert [process.command for process in launcher.started] == [[str(Path("panel")), "--profile", "gta2"]]


def test_a_dock_opens_it_beside_the_desktop_window() -> None:
    launcher = FakeLauncher()
    panels = PanelWindows(Path("panel"), launcher, FakeFronter())

    panels.open("gta2", lambda: Dock("left", 900, -20, 1300))

    assert launcher.started[0].command[3:] == [
        "--dock-side",
        "left",
        "--dock-x",
        "900",
        "--dock-y",
        "-20",
        "--dock-height",
        "1300",
    ]


def test_where_the_dock_cannot_be_told_it_opens_centered() -> None:
    launcher = FakeLauncher()
    panels = PanelWindows(Path("panel"), launcher, FakeFronter())

    panels.open("gta2", lambda: None)

    assert launcher.started[0].command == [str(Path("panel")), "--profile", "gta2"]


def test_a_profile_has_at_most_one_window_while_it_is_open() -> None:
    launcher = FakeLauncher()
    panels = PanelWindows(Path("panel"), launcher, FakeFronter())

    panels.open("gta2")
    panels.open("gta2")
    panels.open("mad-max")

    assert len(launcher.started) == 2

    launcher.started[0].exit_code = 0
    panels.open("gta2")

    assert len(launcher.started) == 3


def test_opening_a_window_already_open_brings_it_to_the_front() -> None:
    launcher = FakeLauncher()
    fronter = FakeFronter()
    panels = PanelWindows(Path("panel"), launcher, fronter)
    panels.open("gta2")
    panels.open("mad-max")

    asked: list[str] = []

    def dock() -> Dock:
        asked.append("dock")
        return Dock("right", 0, 0, 600)

    panels.open("gta2", dock)

    assert fronter.brought == [launcher.started[0].pid]
    assert len(launcher.started) == 2
    # Only a window that opens needs to know where.
    assert asked == []

    launcher.started[0].exit_code = 0
    panels.open("gta2")

    assert fronter.brought == [launcher.started[0].pid]


def test_closing_all_ends_the_windows_still_open() -> None:
    launcher = FakeLauncher()
    panels = PanelWindows(Path("panel"), launcher, FakeFronter())
    panels.open("gta2")
    panels.open("mad-max")
    launcher.started[1].exit_code = 0

    panels.close_all()

    assert [process.terminated for process in launcher.started] == [True, False]


def test_without_the_program_nothing_opens() -> None:
    with pytest.raises(RuntimeError):
        PanelWindows(None, FakeLauncher(), FakeFronter()).open("gta2")
