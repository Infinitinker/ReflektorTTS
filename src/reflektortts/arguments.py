"""Command line options, the same for the console command and the desktop app."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from reflektortts.core import default_profiles_dir


@dataclass(frozen=True)
class Arguments:
    profiles: Path
    """Folder with app profiles."""
    overlay: tuple[Path, ...]
    """Folders with overlay builds, e.g. 32- and 64-bit."""


def parse_arguments(program: str, argv: list[str] | None = None) -> Arguments:
    parser = argparse.ArgumentParser(prog=program, description="Your app, read aloud.")
    parser.add_argument(
        "--profiles",
        type=Path,
        default=default_profiles_dir(),
        help="folder with app profiles (default: %(default)s)",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        action="append",
        default=[],
        help="folder with an overlay build to load into apps (DLL and injector); repeat for 32- and 64-bit builds",
    )
    args = parser.parse_args(argv)
    return Arguments(profiles=args.profiles, overlay=tuple(args.overlay))
