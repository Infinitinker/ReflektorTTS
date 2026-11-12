"""Tests for the per-user folders: named after this ReflektorTTS, lowercase on Windows, the system's own elsewhere."""

import sys

import platformdirs
import pytest

from reflektortts import user_dirs
from reflektortts.identity import MODE_VARIABLE


@pytest.fixture(autouse=True)
def end_to_end_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs as ReflektorTTS E2E, a name these tests can tell from the others."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv(MODE_VARIABLE, "e2e")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows folders")
def test_logs_and_cache_are_lowercase_in_the_app_folder_on_windows() -> None:
    assert user_dirs.data_dir().name == "ReflektorTTS E2E"
    assert user_dirs.log_dir() == user_dirs.data_dir() / "logs"
    assert user_dirs.cache_dir() == user_dirs.data_dir() / "cache"


@pytest.mark.skipif(sys.platform == "win32", reason="Linux folders")
def test_logs_and_cache_are_the_systems_own_elsewhere() -> None:
    assert user_dirs.log_dir() == platformdirs.user_log_path("ReflektorTTS E2E", appauthor=False)
    assert user_dirs.cache_dir() == platformdirs.user_cache_path("ReflektorTTS E2E", appauthor=False)
    assert user_dirs.log_dir().parts[-2:] == ("ReflektorTTS E2E", "log")


def test_each_folder_is_named_after_this_reflektortts() -> None:
    for folder in (user_dirs.config_dir(), user_dirs.data_dir(), user_dirs.state_dir(), user_dirs.cache_dir()):
        assert "ReflektorTTS E2E" in folder.parts


def test_a_release_keeps_the_installed_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert "ReflektorTTS" in user_dirs.data_dir().parts
    assert "ReflektorTTS E2E" not in user_dirs.data_dir().parts
