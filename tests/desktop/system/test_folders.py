"""Opening folders and files in the file manager, and how the app's folders are shown to the user."""

import sys
from pathlib import Path

import pytest

from reflektortts.desktop.system import folders


def test_explorer_is_started_by_its_full_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started: list[list[str]] = []
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("SystemRoot", r"D:\Windows")
    monkeypatch.setattr("subprocess.Popen", started.append)

    folders.open_folder(tmp_path / "logs")
    folders.show_file(tmp_path / "a.json")

    explorer = str(Path(r"D:\Windows") / "explorer.exe")
    assert started == [[explorer, str(tmp_path / "logs")], [explorer, f"/select,{tmp_path / 'a.json'}"]]
    assert (tmp_path / "logs").is_dir()


def test_a_folder_in_local_app_data_is_shown_without_the_users_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert folders.shown_path(tmp_path / "ReflektorTTS") == str(Path("%LOCALAPPDATA%", "ReflektorTTS"))


def test_a_folder_in_the_home_folder_is_shown_from_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert folders.shown_path(tmp_path / ".config" / "ReflektorTTS") == str(Path("~", ".config", "ReflektorTTS"))


def test_one_folder_for_everything_is_named_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(folders, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(folders, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(folders, "log_dir", lambda: tmp_path / "logs")

    shown = folders.shown_path(tmp_path)
    assert folders.where_files_are() == (
        f"Settings, downloaded voices and models, your own profiles and the logs are kept in {shown}."
    )


def test_separate_folders_are_each_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(folders, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(folders, "data_dir", lambda: tmp_path / "share")
    monkeypatch.setattr(folders, "log_dir", lambda: tmp_path / "state" / "log")

    text = folders.where_files_are()

    assert folders.shown_path(tmp_path / "config") in text
    assert folders.shown_path(tmp_path / "share") in text
    assert folders.shown_path(tmp_path / "state" / "log") in text
