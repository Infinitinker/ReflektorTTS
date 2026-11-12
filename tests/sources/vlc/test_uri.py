"""The file a VLC media URI names: Windows and POSIX file URIs, and media that are not files."""

import sys
from pathlib import Path

import pytest

from reflektortts.sources.vlc.uri import uri_to_path

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows paths")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")


@windows_only
@pytest.mark.parametrize(
    ("uri", "path"),
    [
        ("file:///C:/Media/Test%20%C4%85%C4%99%20%231/movie.wav", "C:\\Media\\Test ąę #1\\movie.wav"),
        ("file://localhost/C:/Media/movie.mkv", "C:\\Media\\movie.mkv"),
        ("file:///C:/Media/a%2520b.mkv", "C:\\Media\\a%20b.mkv"),
        ("file://nas/films/F%C3%A9e.mkv", "\\\\nas\\films\\Fée.mkv"),
        ("file:///C:/Media/movie.mkv?start=10#t=5", "C:\\Media\\movie.mkv"),
    ],
)
def test_windows_file_uris_become_the_paths_vlc_opens(uri: str, path: str) -> None:
    assert uri_to_path(uri) == Path(path)


@posix_only
def test_posix_file_uris_are_decoded_too() -> None:
    assert uri_to_path("file:///home/user/Test%20%C4%85%20%231/a%2520b.mkv") == Path("/home/user/Test ą #1/a%20b.mkv")


@pytest.mark.parametrize("uri", ["http://example.com/stream.mp3", "dvd:///D:/", "screen://"])
def test_other_media_are_not_files(uri: str) -> None:
    assert uri_to_path(uri) is None
