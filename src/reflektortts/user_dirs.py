"""The per-user folders ReflektorTTS keeps its files in, named after this ReflektorTTS (see
identity.py): e.g. %LOCALAPPDATA%\\ReflektorTTS on Windows, and %LOCALAPPDATA%\\ReflektorTTS Dev for a run
from source."""

import sys
from pathlib import Path

import platformdirs

from reflektortts.identity import app_name


def config_dir() -> Path:
    return platformdirs.user_config_path(app_name(), appauthor=False)


def data_dir() -> Path:
    return platformdirs.user_data_path(app_name(), appauthor=False)


def profiles_dir() -> Path:
    """The user's own profiles, next to the bundled ones."""
    return data_dir() / "profiles"


def state_dir() -> Path:
    return platformdirs.user_state_path(app_name(), appauthor=False)


def log_dir() -> Path:
    """%LOCALAPPDATA%\\ReflektorTTS\\logs on Windows, lowercase like every folder of ours, where
    platformdirs would say Logs; elsewhere platformdirs' folder, e.g. ~/.local/state/ReflektorTTS/log."""
    if sys.platform == "win32":
        return data_dir() / "logs"
    return platformdirs.user_log_path(app_name(), appauthor=False)


def cache_dir() -> Path:
    """For files that can be fetched again, e.g. lists of downloadable voices: on Windows
    %LOCALAPPDATA%\\ReflektorTTS\\cache, where platformdirs would say Cache; elsewhere platformdirs' folder."""
    if sys.platform == "win32":
        return data_dir() / "cache"
    return platformdirs.user_cache_path(app_name(), appauthor=False)
