"""Tests for the per-user folders: lowercase on Windows, the system's own elsewhere."""

import sys
from pathlib import Path

import platformdirs
import pytest

from reflektortts import user_dirs


@pytest.mark.skipif(sys.platform != "win32", reason="Windows folders")
def test_logs_and_cache_are_lowercase_in_the_app_folder_on_windows() -> None:
    assert user_dirs.log_dir() == user_dirs.data_dir() / "logs"
    assert user_dirs.cache_dir() == user_dirs.data_dir() / "cache"
    assert user_dirs.data_dir().name == "ReflektorTTS"


@pytest.mark.skipif(sys.platform == "win32", reason="Linux folders")
def test_logs_and_cache_are_the_systems_own_elsewhere() -> None:
    assert user_dirs.log_dir() == platformdirs.user_log_path("ReflektorTTS", appauthor=False)
    assert user_dirs.cache_dir() == platformdirs.user_cache_path("ReflektorTTS", appauthor=False)
    assert user_dirs.log_dir().parts[-2:] == ("ReflektorTTS", "log")


def test_each_folder_is_named_after_the_app() -> None:
    for folder in (user_dirs.config_dir(), user_dirs.data_dir(), user_dirs.state_dir()):
        assert "ReflektorTTS" in Path(folder).parts
