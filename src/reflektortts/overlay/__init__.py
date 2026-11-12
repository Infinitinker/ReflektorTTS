"""Loading the overlay into an app; one implementation per OS, so far only Windows' (windows.py)."""

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


def inject_overlay(pid: int, overlay_dirs: Sequence[Path], api_port: int) -> bool:
    """Loads the overlay into the app with process ID pid, trying each overlay build in turn (e.g.
    32-bit, then 64-bit) until one matches the app, and returns whether one did. The overlay
    connects to the local API on api_port. A failure is logged, and the app is read without the
    overlay."""
    if sys.platform == "win32":
        from reflektortts.overlay.windows import inject

        return inject(pid, overlay_dirs, api_port)
    logger.warning("The overlay is not available on this system yet; the app is read without it.")
    return False
