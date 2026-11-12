"""Downloading a file: what the user is told when the server, the connection or saving it fails."""

import io
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from reflektortts.downloads import http
from reflektortts.downloads.source import DownloadError

URL = "https://example.com/voice.onnx"


class Response(io.BytesIO):
    """An answer whose body is data, or that fails with error after the first block."""

    def __init__(self, data: bytes, error: Exception | None = None) -> None:
        super().__init__(data)
        self.headers = Message()
        self.headers["Content-Length"] = str(len(data))
        self._error = error

    def read(self, size: int | None = -1) -> bytes:
        if self._error is not None and self.tell() > 0:
            raise self._error
        return super().read(size)


def answering(monkeypatch: pytest.MonkeyPatch, answer: Response | Exception) -> None:
    def urlopen(request: Any, timeout: float) -> Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def download(tmp_path: Path) -> list[tuple[int, int | None]]:
    reported: list[tuple[int, int | None]] = []
    http.download(URL, tmp_path / "voice.onnx", lambda done, total: reported.append((done, total)))
    return reported


def test_the_file_is_saved_and_its_progress_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, Response(b"x" * (http.BLOCK + 1)))

    reported = download(tmp_path)

    assert (tmp_path / "voice.onnx").read_bytes() == b"x" * (http.BLOCK + 1)
    assert reported == [(http.BLOCK, http.BLOCK + 1), (http.BLOCK + 1, http.BLOCK + 1)]


def test_a_missing_file_says_it_may_have_moved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, urllib.error.HTTPError(URL, 404, "Not Found", Message(), None))

    with pytest.raises(http.NotFoundError, match="was not found: it may have moved"):
        download(tmp_path)


def test_a_server_error_names_the_answer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, urllib.error.HTTPError(URL, 503, "Service Unavailable", Message(), None))

    with pytest.raises(DownloadError, match="the server answered 503 Service Unavailable. Try again later.") as raised:
        download(tmp_path)
    assert "internet connection" not in str(raised.value)


@pytest.mark.parametrize("error", [urllib.error.URLError("getaddrinfo failed"), TimeoutError("timed out")])
def test_no_connection_says_to_check_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception) -> None:
    answering(monkeypatch, error)

    with pytest.raises(DownloadError, match="Check your internet connection, then try again."):
        download(tmp_path)


def test_a_connection_lost_while_reading_says_to_check_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, Response(b"x" * (http.BLOCK * 2), ConnectionResetError(10054, "reset")))

    with pytest.raises(DownloadError, match="Check your internet connection, then try again."):
        download(tmp_path)


def test_a_file_that_cannot_be_saved_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, Response(b"x"))

    with pytest.raises(DownloadError, match=r"could not be saved in .*\(.*\): check the free space") as raised:
        http.download(URL, tmp_path / "missing" / "voice.onnx", lambda done, total: None)
    assert "internet connection" not in str(raised.value)


def test_a_full_disk_says_the_file_could_not_be_saved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    answering(monkeypatch, Response(b"x"))
    real_open = Path.open

    class FullDisk(io.BytesIO):
        def write(self, data: Any) -> int:
            raise OSError(28, "No space left on device")

    def open_full(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        return FullDisk() if mode == "wb" else real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_full)

    with pytest.raises(DownloadError, match=r"could not be saved in .* \(No space left on device\)"):
        download(tmp_path)
