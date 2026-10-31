"""Where logs go: the console, or files in the user's log folder when there is no console."""

import logging
import logging.handlers
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 1024 * 1024
BACKUPS = 3


def log_to_console() -> None:
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    _quiet_requests()


def log_to_file(path: Path) -> None:
    """Logs to path, starting a new file at about 1 MB and keeping the last few."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _quiet_requests()


def file_log_dir() -> Path | None:
    """The folder this process logs files to, if it does; other processes it starts log there too."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            return Path(handler.baseFilename).parent
    return None


def _quiet_requests() -> None:
    # One line per API request would drown the log the user reads.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
