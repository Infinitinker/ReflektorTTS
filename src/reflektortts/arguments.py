"""Command line options, the same for the console command and the desktop app."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from reflektortts.core import default_profiles_dir


@dataclass(frozen=True)
class Arguments:
    profiles: Path
    """Folder with app profiles."""
    overlay: tuple[Path, ...]
    """Folders with overlay builds, e.g. 32- and 64-bit."""
    hidden: bool = False
    """The desktop app starts with only its tray icon, as when Windows starts it at sign-in."""


def parse_arguments(program: str, argv: list[str] | None = None, desktop: bool = False) -> Arguments:
    """desktop adds the desktop app's own options."""
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
        help="folder with an overlay build to load into apps (DLL and injector); repeat for 32- and 64-bit "
        "builds (default: the ones next to ReflektorTTS.exe in a release, none otherwise)",
    )
    if desktop:
        parser.add_argument("--hidden", action="store_true", help="start with only the icon next to the clock")
    args = parser.parse_args(argv)
    return Arguments(
        profiles=args.profiles,
        overlay=tuple(args.overlay or default_overlay_dirs()),
        hidden=desktop and args.hidden,
    )


def default_overlay_dirs() -> list[Path]:
    """In a release (a frozen ReflektorTTS.exe), the 32- and 64-bit overlay builds in the overlay
    folder next to it (x86 and x64); run from source, there is no default."""
    if not getattr(sys, "frozen", False):
        return []
    overlay = Path(sys.executable).parent / "overlay"
    return [overlay / "x86", overlay / "x64"]
