"""Files on a pretend internet, for download source tests."""

from pathlib import Path

from reflektortts.downloads.http import NotFoundError
from reflektortts.downloads.source import DownloadError, Progress


class FakeWeb:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.fetched: list[str] = []
        self.offline = False

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        if self.offline:
            raise DownloadError(f"Could not reach {url}. Check your internet connection.")
        if url not in self.files:
            raise NotFoundError(f"{url} was not found.")
        return self.files[url]

    def download(self, url: str, destination: Path, progress: Progress) -> None:
        data = self.fetch(url)
        destination.write_bytes(data)
        progress(len(data), len(data))

    def size(self, url: str) -> int | None:
        return len(self.files[url]) if url in self.files else None
