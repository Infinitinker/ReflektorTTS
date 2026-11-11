"""Desktop app entry point: reflektortts-desktop, or pythonw -m reflektortts.desktop."""

import logging
import multiprocessing
import sys
import tkinter as tk
from types import TracebackType

from reflektortts.arguments import parse_arguments
from reflektortts.desktop.application import Application
from reflektortts.desktop.system.session import announce_running
from reflektortts.desktop.widgets.theme import draws_without_xft
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
    if draws_without_xft(root):
        logger.warning(
            'This Python\'s Tk draws text without Xft, so letters such as "ł" or "…" show as wrong symbols in '
            "the window: run ReflektorTTS with a Python whose Tk has Xft, such as your distribution's with python3-tk"
        )
    Application(root, args).start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
