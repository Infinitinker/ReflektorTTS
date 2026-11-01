"""Lists of downloads, kept on disk so they also show without an internet connection."""

import logging
import os
from collections.abc import Callable
from pathlib import Path

from reflektortts.downloads.source import DownloadError

logger = logging.getLogger(__name__)


def cached(path: Path, fetch: Callable[[], bytes], refresh: bool) -> bytes:
    """The file at path, fetched again first if refresh or if there is none yet. If fetching
    fails, the saved copy is used; without one, the error is raised."""
    if path.is_file() and not refresh:
        return path.read_bytes()
    try:
        data = fetch()
    except DownloadError as error:
        if not path.is_file():
            raise
        logger.warning("%s Showing the list saved earlier.", error)
        return path.read_bytes()
    save(path, data)
    return data


def save(path: Path, data: bytes) -> None:
    """Writes through a temporary file, so a crash never leaves a half-written list."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
