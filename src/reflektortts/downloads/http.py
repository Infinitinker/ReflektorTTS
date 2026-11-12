"""Fetching lists and files over HTTPS, for download sources."""

import http.client
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from reflektortts.downloads.source import DownloadError, Progress

logger = logging.getLogger(__name__)

USER_AGENT = "ReflektorTTS"
"""Some servers (argos-net.com) refuse Python's default User-Agent."""
TIMEOUT = 30
BLOCK = 1 << 16
PARALLEL_REQUESTS = 8
"""How many of a list's small requests (sizes, model cards) are made at once."""


class NotFoundError(DownloadError):
    """The server is reached but has no such file."""


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=method)


def fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response:
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFoundError(f"{url} was not found: it may have moved. Try again later.") from error
        raise DownloadError(f"Could not fetch {url}: the server answered {error.code} {error.reason}.") from error
    except (urllib.error.URLError, OSError) as error:
        logger.debug("Could not reach %s: %s", url, error)  # Logged where the error is shown or used.
        raise DownloadError(
            f"Could not reach {url}. Check your internet connection, then close and open the window again."
        ) from error


def content_length(url: str) -> int | None:
    """The size the server reports for a file, if it does."""
    try:
        with urllib.request.urlopen(_request(url, "HEAD"), timeout=TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            return int(length) if length and length.isdigit() else None
    except (urllib.error.URLError, OSError):
        return None


def each[T, R](function: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """function's result for each item, in order, PARALLEL_REQUESTS at a time."""
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        return list(pool.map(function, items))


def download(url: str, destination: Path, progress: Progress) -> None:
    """Streams a file to destination, reporting progress as it goes. The error says which failed:
    the server, the connection or saving the file."""
    try:
        response = urllib.request.urlopen(_request(url), timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        logger.warning("Could not download %s: %s", url, error)
        if error.code == 404:
            raise NotFoundError(f"{url} was not found: it may have moved. Try again later.") from error
        raise DownloadError(
            f"Could not download {url}: the server answered {error.code} {error.reason}. Try again later."
        ) from error
    except (urllib.error.URLError, OSError) as error:
        raise _connection_lost(url, error) from error
    with response:
        try:
            file = destination.open("wb")
        except OSError as error:
            raise _not_saved(destination, error) from error
        with file:
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            done = 0
            while True:
                try:
                    block = response.read(BLOCK)
                except (OSError, http.client.HTTPException) as error:  # A timeout, a reset, a cut-off answer.
                    raise _connection_lost(url, error) from error
                if not block:
                    break
                try:
                    file.write(block)
                except OSError as error:
                    raise _not_saved(destination, error) from error
                done += len(block)
                progress(done, total)


def _connection_lost(url: str, error: Exception) -> DownloadError:
    logger.warning("Could not download %s: %s", url, error)
    return DownloadError(f"Could not download {url}. Check your internet connection, then try again.")


def _not_saved(destination: Path, error: OSError) -> DownloadError:
    logger.warning("Could not save %s: %s", destination, error)
    reason = error.strerror or type(error).__name__
    return DownloadError(
        f"The download could not be saved in {destination.parent} ({reason}): check the free space on the "
        "drive, then try again."
    )
