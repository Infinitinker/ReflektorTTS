"""The per-user folders ReflektorTTS keeps its files in, e.g. %LOCALAPPDATA%\\ReflektorTTS on Windows."""

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
    return platformdirs.user_log_path(APP_DIR, appauthor=False)


def cache_dir() -> Path:
    """For files that can be fetched again, e.g. lists of downloadable voices."""
    return platformdirs.user_cache_path(APP_DIR, appauthor=False)
