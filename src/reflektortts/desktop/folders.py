"""Opens folders and files in the system's file manager."""

import subprocess
import sys
from pathlib import Path


def open_folder(path: Path) -> None:
    """Shows the folder, creating it if needed."""
    path.mkdir(parents=True, exist_ok=True)
    # Explorer itself, not os.startfile: on some Windows set-ups the shell accepts a request to
    # open a folder and shows nothing, even from a plain script.
    command = ["explorer", str(path)] if sys.platform == "win32" else ["xdg-open", str(path)]
    subprocess.Popen(command)


def show_file(path: Path) -> None:
    """Shows the folder with the file selected, where the system can do that."""
    command = ["explorer", f"/select,{path}"] if sys.platform == "win32" else ["xdg-open", str(path.parent)]
    subprocess.Popen(command)
