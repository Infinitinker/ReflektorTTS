"""Opens folders and files in the system's file manager."""

import os
import subprocess
import sys
from pathlib import Path

from reflektortts.user_dirs import config_dir, data_dir, log_dir


def explorer() -> str:
    """Explorer by its full path: by name alone, Windows would first look for an explorer.exe in
    ReflektorTTS's folder and the current folder, where anyone could have put one."""
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe")


def shown_path(path: Path) -> str:
    """The path as the user would write it: on Windows %LOCALAPPDATA%\\..., elsewhere ~/...; shorter,
    and without the user's name."""
    local = os.environ.get("LOCALAPPDATA")
    if sys.platform == "win32" and local and path.is_relative_to(local):
        return str(Path("%LOCALAPPDATA%", path.relative_to(local)))
    if path.is_relative_to(Path.home()):
        return str(Path("~", path.relative_to(Path.home())))
    return str(path)


def where_files_are() -> str:
    """Where ReflektorTTS keeps the user's files, in a sentence: one folder on Windows, several on Linux."""
    if config_dir() == data_dir() and log_dir().is_relative_to(config_dir()):
        return (
            "Settings, downloaded voices and models, your own profiles and the logs are kept in "
            f"{shown_path(config_dir())}."
        )
    return (
        f"Settings are kept in {shown_path(config_dir())}, downloaded voices and models and your own "
        f"profiles in {shown_path(data_dir())}, and the logs in {shown_path(log_dir())}."
    )


def open_folder(path: Path) -> None:
    """Shows the folder, creating it if needed."""
    path.mkdir(parents=True, exist_ok=True)
    # Explorer itself, not os.startfile: on some Windows set-ups the shell accepts a request to
    # open a folder and shows nothing, even from a plain script.
    command = [explorer(), str(path)] if sys.platform == "win32" else ["xdg-open", str(path)]
    subprocess.Popen(command)


def show_file(path: Path) -> None:
    """Shows the folder with the file selected, where the system can do that."""
    command = [explorer(), f"/select,{path}"] if sys.platform == "win32" else ["xdg-open", str(path.parent)]
    subprocess.Popen(command)
