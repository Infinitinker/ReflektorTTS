"""The folders of the end-to-end test: its output folder, cleared before each run, and inside it
the per-user folders ReflektorTTS and VLC are given instead of the real ones.

The per-user folders move through environment variables that platformdirs reads, so ReflektorTTS
runs unchanged: on Windows WIN_PD_OVERRIDE_LOCAL_APPDATA (settings, profiles, logs, downloads) and
WIN_PD_OVERRIDE_APPDATA (VLC's settings), on Linux the XDG base directories.
"""

import os
import shutil
import sys
import time
from pathlib import Path

from reflektortts.identity import NAMES

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = Path(os.environ.get("E2E_OUTPUT") or ROOT / "build" / "e2e").resolve()
"""Where the report, the logs and the test's files go: E2E_OUTPUT, or build/e2e in the repository.
Absolute, since platformdirs ignores a relative folder, and the app would then use the real ones."""
HOME = OUTPUT / "home"
"""The per-user folders of the run."""
MEDIA = OUTPUT / "media"
"""The video the fake VLC plays, and its subtitles."""
FAKE_VLC = OUTPUT / "vlc"
"""The program the fake VLC runs as."""


def user_folders() -> dict[str, str]:
    """The environment variables that move the per-user folders into HOME."""
    if sys.platform == "win32":
        return {"WIN_PD_OVERRIDE_LOCAL_APPDATA": str(HOME / "Local"), "WIN_PD_OVERRIDE_APPDATA": str(HOME / "Roaming")}
    return {f"XDG_{kind.upper()}_HOME": str(HOME / kind) for kind in ("config", "data", "state", "cache")}


def log_folder() -> Path:
    """Where ReflektorTTS writes its logs in a run (log_dir in user_dirs.py)."""
    if sys.platform == "win32":
        return HOME / "Local" / NAMES["e2e"] / "logs"
    return HOME / "state" / NAMES["e2e"] / "log"


def vlcrc() -> Path:
    """VLC's settings file, where vlcrc.vlcrc_path finds it in a run."""
    if sys.platform == "win32":
        return HOME / "Roaming" / "vlc" / "vlcrc"
    return HOME / "config" / "vlc" / "vlcrc"


def clear_output() -> None:
    """Deletes the output of the last run. The retries cover files a stopped process holds for a moment on Windows."""
    for attempt in range(10):
        try:
            shutil.rmtree(OUTPUT)
            break
        except FileNotFoundError:
            break
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.5)
    OUTPUT.mkdir(parents=True)
