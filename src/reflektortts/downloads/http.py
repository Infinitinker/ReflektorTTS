"""Fetching lists and files over HTTPS, for download sources."""

import urllib.error
import urllib.request
from pathlib import Path

from reflektortts.downloads.source import DownloadError, Progress

USER_AGENT = "ReflektorTTS"
"""Some servers (argos-net.com) refuse Python's default User-Agent."""
TIMEOUT = 30
BLOCK = 1 << 16


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=method)


def fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response:
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, OSError) as error:
        raise DownloadError(f"Could not reach {url}: {error}. Check your internet connection.") from error


def content_length(url: str) -> int | None:
    """The size the server reports for a file, if it does."""
    try:
        with urllib.request.urlopen(_request(url, "HEAD"), timeout=TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            return int(length) if length and length.isdigit() else None
    except (urllib.error.URLError, OSError):
        return None


def download(url: str, destination: Path, progress: Progress) -> None:
    """Streams a file to destination, reporting progress as it goes."""
    try:
        with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response, destination.open("wb") as file:
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            done = 0
            while block := response.read(BLOCK):
                file.write(block)
                done += len(block)
                progress(done, total)
    except (urllib.error.URLError, OSError) as error:
        raise DownloadError(f"Could not download {url}: {error}. Check your internet connection.") from error
