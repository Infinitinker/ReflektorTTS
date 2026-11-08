"""VLC's web interface as the client sees it, answering from data taken from VLC 3.0.23 (paths
changed), or failing as asked."""

import json
import urllib.request
from typing import Any

STATUS: dict[str, Any] = {
    "fullscreen": 0,
    "seek_sec": 10,
    "apiversion": 3,
    "currentplid": 2,
    "time": 8,
    "volume": 256,
    "length": 120,
    "random": False,
    "rate": 1,
    "state": "playing",
    "loop": False,
    "version": "3.0.23 Vetinari",
    "position": 0.070424996316433,
    "audiodelay": 0,
    "repeat": False,
    "subtitledelay": 0,
}
"""Captured while a 120 s file played, 8 s in."""


def playlist(*leaves: tuple[int, str]) -> dict[str, Any]:
    """A playlist with these items (ID, URI), shaped as VLC's: the root, then the playlist node."""
    children = [
        {"ro": "rw", "type": "leaf", "name": uri.rpartition("/")[2], "id": str(item), "duration": 120, "uri": uri}
        for item, uri in leaves
    ]
    return {
        "ro": "rw",
        "type": "node",
        "name": "",
        "id": "0",
        "children": [{"ro": "ro", "type": "node", "name": "Lista odtwarzania", "id": "1", "children": children}],
    }


class FakeVlc:
    """An OpenUrl answering /requests/status.json and /requests/playlist.json."""

    def __init__(self) -> None:
        self.status: dict[str, Any] = dict(STATUS)
        self.playlist: dict[str, Any] = playlist((2, "file:///C:/Media/Test%20%C4%85%C4%99%20%231/movie.wav"))
        self.failure: Exception | None = None
        """What every request raises, or None to answer."""
        self.body: bytes | None = None
        """What every request is answered with instead of JSON, or None."""
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> bytes:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.failure is not None:
            raise self.failure
        if self.body is not None:
            return self.body
        path = request.full_url.partition("127.0.0.1")[2].partition("/")[2]
        answers = {"requests/status.json": self.status, "requests/playlist.json": self.playlist}
        return json.dumps(answers[path]).encode()

    def paths(self) -> list[str]:
        return ["/" + request.full_url.split("/", 3)[3] for request in self.requests]
