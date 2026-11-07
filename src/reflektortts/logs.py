"""Where logs go: the console, or files in the user's log folder when there is no console."""

import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from types import TracebackType

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 1024 * 1024
BACKUPS = 3


def log_to_console() -> None:
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    _quiet_requests()


def log_to_file(path: Path) -> None:
    """Logs to path, starting a new file at about 1 MB and keeping the last few, with the errors
    no code catches, which would otherwise go to a console the process does not have."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _quiet_requests()
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread


def file_log_dir() -> Path | None:
    """The folder this process logs files to, if it does; other processes it starts log there too."""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            return Path(handler.baseFilename).parent
    return None


def _quiet_requests() -> None:
    # One line per API request would drown the log the user reads.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _log_uncaught(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
    logging.getLogger(__name__).error("Uncaught error", exc_info=(kind, error, trace))


def _log_uncaught_in_thread(hook: threading.ExceptHookArgs) -> None:
    if hook.exc_type is SystemExit or hook.exc_value is None:
        return
    name = hook.thread.name if hook.thread else "unknown"
    logging.getLogger(__name__).error(
        "Uncaught error in the thread %s", name, exc_info=(hook.exc_type, hook.exc_value, hook.exc_traceback)
    )
