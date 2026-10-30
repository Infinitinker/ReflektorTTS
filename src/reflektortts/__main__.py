"""Command line entry point: python -m reflektortts."""

import argparse
import logging
import sys
import threading
from pathlib import Path

from reflektortts.app import default_profiles_dir, run
from reflektortts.tts.engine import DEFAULT_VOICE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reflektortts", description="Your game, read aloud.")
    parser.add_argument(
        "--profiles",
        type=Path,
        default=default_profiles_dir(),
        help="folder with game profiles (default: %(default)s)",
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help='voice as engine:name, e.g. "windows:Microsoft Adam" (default: %(default)s)',
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run(args.profiles, args.voice, threading.Event())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
