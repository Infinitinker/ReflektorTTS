"""Command line entry point: python -m reflektortts."""

import argparse
import logging
import sys
import threading
from pathlib import Path

from reflektortts.api.server import ApiError
from reflektortts.app import default_profiles_dir, run
from reflektortts.user_dirs import config_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reflektortts", description="Your game, read aloud.")
    parser.add_argument(
        "--profiles",
        type=Path,
        default=default_profiles_dir(),
        help="folder with game profiles (default: %(default)s)",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        action="append",
        default=[],
        help="folder with an overlay build to load into games (DLL and injector); repeat for 32- and 64-bit builds",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # One line per API request would drown the log the user reads.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    log = logging.getLogger(__name__)
    log.info("Settings: %s (each game's are set in the in-game overlay or through the API)", config_dir())
    try:
        run(args.profiles, config_dir(), args.overlay, threading.Event())
    except ApiError as error:
        log.error("%s", error)
        return 1
    except KeyboardInterrupt:
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
