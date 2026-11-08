"""Desktop app entry point: reflektortts-desktop, or pythonw -m reflektortts.desktop."""

import logging
import multiprocessing
import sys
import tkinter as tk
from types import TracebackType

from reflektortts.arguments import parse_arguments
from reflektortts.desktop.application import Application
from reflektortts.desktop.system.session import announce_running
from reflektortts.logs import log_to_file
from reflektortts.user_dirs import config_dir, log_dir

LOG_FILE = "reflektortts.log"

logger = logging.getLogger(__name__)


def log_callback_error(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
    """Tkinter prints errors in button and timer callbacks to a console the app does not have."""
    logger.error("Error in the window", exc_info=(kind, error, trace))


def main(argv: list[str] | None = None) -> int:
    # In ReflektorTTS.exe, the speech process starts as another run of the exe; this lets it.
    multiprocessing.freeze_support()
    args = parse_arguments("reflektortts-desktop", argv, desktop=True)
    log_to_file(log_dir() / LOG_FILE)
    logger.info("Started; settings in %s, logs in %s", config_dir(), log_dir())
    announce_running()
    root = tk.Tk()
    root.report_callback_exception = log_callback_error
    Application(root, args).start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
