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
