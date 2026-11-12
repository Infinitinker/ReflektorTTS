"""The per-user folders ReflektorTTS keeps its files in, e.g. %LOCALAPPDATA%\\ReflektorTTS on Windows."""

import sys
from pathlib import Path

import platformdirs

APP_DIR = "ReflektorTTS"


def config_dir() -> Path:
    return platformdirs.user_config_path(APP_DIR, appauthor=False)


def data_dir() -> Path:
    return platformdirs.user_data_path(APP_DIR, appauthor=False)


def state_dir() -> Path:
    return platformdirs.user_state_path(APP_DIR, appauthor=False)


def log_dir() -> Path:
    """%LOCALAPPDATA%\\ReflektorTTS\\logs on Windows, lowercase like every folder of ours, where
    platformdirs would say Logs; elsewhere platformdirs' folder, e.g. ~/.local/state/ReflektorTTS/log."""
    if sys.platform == "win32":
        return data_dir() / "logs"
    return platformdirs.user_log_path(APP_DIR, appauthor=False)


def cache_dir() -> Path:
    """For files that can be fetched again, e.g. lists of downloadable voices: on Windows
    %LOCALAPPDATA%\\ReflektorTTS\\cache, where platformdirs would say Cache; elsewhere platformdirs' folder."""
    if sys.platform == "win32":
        return data_dir() / "cache"
    return platformdirs.user_cache_path(APP_DIR, appauthor=False)
