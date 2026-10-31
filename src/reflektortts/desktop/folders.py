"""Opens a folder in the system's file manager."""

import os
import subprocess
import sys
from pathlib import Path


def open_folder(path: Path) -> None:
    """Shows the folder, creating it if needed."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])
