"""Command line entry point: python -m reflektortts."""

import logging
import sys
import threading

from reflektortts.api.server import ApiError
from reflektortts.arguments import parse_arguments
from reflektortts.core import NoProfilesError, run
from reflektortts.logs import log_to_console
from reflektortts.user_dirs import config_dir


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments("reflektortts", argv)
    log_to_console()
    log = logging.getLogger(__name__)
    log.info("Settings: %s (each app's are set in the overlay or through the API)", config_dir())
    try:
        run(args.profiles, config_dir(), args.overlay, threading.Event())
    except (ApiError, NoProfilesError) as error:
        log.error("%s", error)
        return 1
    except KeyboardInterrupt:
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
