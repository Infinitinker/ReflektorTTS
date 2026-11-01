"""Staging folders: where downloads and installs are put together before they replace what is
installed, so a failed one never leaves a broken install behind."""

import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PREFIX = ".staging-"


def staging_folder(parent: Path) -> tempfile.TemporaryDirectory[str]:
    """A folder in parent, removed when done; parent is created if needed."""
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=PREFIX, dir=parent)


def remove_leftovers(parent: Path) -> None:
    """Removes staging folders left in parent by a download cut off midway, e.g. by quitting
    ReflektorTTS. Call it only while nothing is being downloaded into parent."""
    for folder in parent.glob(f"{PREFIX}*"):
        try:
            shutil.rmtree(folder)
            logger.info("Removed %s, left by a download that did not finish", folder)
        except OSError as error:
            logger.warning("Cannot remove %s, left by a download that did not finish: %s", folder, error)
