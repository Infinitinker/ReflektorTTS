"""What the desktop app remembers about itself between runs."""

from pathlib import Path

from reflektortts.desktop.system.state import STATE_FILE, DesktopState, load_state, save_state


def test_nothing_is_remembered_at_first(tmp_path: Path) -> None:
    assert load_state(tmp_path) == DesktopState(told_about_tray=False)


def test_the_state_is_remembered_between_runs(tmp_path: Path) -> None:
    save_state(DesktopState(told_about_tray=True), tmp_path)

    assert load_state(tmp_path) == DesktopState(told_about_tray=True)


def test_a_broken_file_gives_the_defaults(tmp_path: Path) -> None:
    (tmp_path / STATE_FILE).write_text("{oops", "utf-8")

    assert load_state(tmp_path) == DesktopState()
