"""Loads the in-game overlay into a game, using the injector built with the overlay."""

import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

INJECTOR = "reflektortts-inject.exe"
# Exit code of the injector when the game and the overlay build differ in bitness.
WRONG_BITNESS = 3


def inject_overlay(pid: int, overlay_dirs: Sequence[Path]) -> bool:
    """Tries each overlay build (e.g. 32-bit, then 64-bit) until one matches the game."""
    for directory in overlay_dirs:
        injector = directory / INJECTOR
        if not injector.is_file():
            logger.error("No overlay injector in %s; check --overlay.", directory)
            continue
        result = subprocess.run(
            [str(injector), "--pid", str(pid)], capture_output=True, text=True, timeout=30, check=False
        )
        if result.returncode == 0:
            logger.info("In-game overlay loaded from %s", directory)
            return True
        if result.returncode != WRONG_BITNESS:
            logger.error("Could not load the in-game overlay: %s", result.stderr.strip())
            return False
    logger.error("No overlay build matches the game (32-bit vs 64-bit); the game runs without the overlay.")
    return False
