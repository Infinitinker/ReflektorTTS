"""Loads the overlay into an app, using the injector built with the overlay."""

import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

INJECTOR = "reflektortts-inject.exe"
# Exit code of the injector when the app and the overlay build differ in bitness.
WRONG_BITNESS = 3
TIMEOUT_S = 30
# Windows errors for a program its antivirus or policy will not let run.
BLOCKED_BY_ANTIVIRUS = {225, 1260}


def inject_overlay(pid: int, overlay_dirs: Sequence[Path]) -> bool:
    """Tries each overlay build (e.g. 32-bit, then 64-bit) until one matches the app.

    A failure is reported and the app is read without the overlay.
    """
    found = False
    for directory in overlay_dirs:
        injector = directory / INJECTOR
        if not injector.is_file():
            logger.error("No overlay in %s.", directory)
            continue
        found = True
        try:
            result = subprocess.run(
                [str(injector), "--pid", str(pid)],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_S,
                check=False,
                # Without a console of its own (the desktop app), Windows would open one for the injector.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            logger.error(
                "The overlay injector did not finish within %d s; the app runs without the overlay.", TIMEOUT_S
            )
            return False
        except OSError as error:
            if getattr(error, "winerror", None) in BLOCKED_BY_ANTIVIRUS:
                logger.error(
                    "Windows blocked the overlay injector (%s) as unwanted software. Overlays work by loading "
                    "into the app, which antivirus programs may distrust; allow it in your antivirus to use "
                    "the overlay. The app is read without it.",
                    injector,
                )
            else:
                logger.error("Could not start the overlay injector %s: %s", injector, error)
            return False
        if result.returncode == 0:
            logger.info("Overlay loaded from %s", directory)
            return True
        if result.returncode != WRONG_BITNESS:
            logger.error("Could not load the overlay: %s", result.stderr.strip())
            return False
    if found:
        logger.error("No overlay build matches the app (32-bit vs 64-bit); the app runs without the overlay.")
    else:
        logger.error("No overlay found; the app runs without the overlay.")
    return False
