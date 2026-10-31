"""Desktop app entry point: reflektortts-app, or pythonw -m reflektortts.desktop."""

import logging
import sys
import tkinter as tk

from reflektortts.arguments import parse_arguments
from reflektortts.desktop.application import Application
from reflektortts.logs import log_to_file
from reflektortts.user_dirs import config_dir, log_dir

LOG_FILE = "reflektortts.log"


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments("reflektortts-app", argv)
    log_to_file(log_dir() / LOG_FILE)
    logging.getLogger(__name__).info("Started; settings in %s, logs in %s", config_dir(), log_dir())
    root = tk.Tk()
    Application(root, args).start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
