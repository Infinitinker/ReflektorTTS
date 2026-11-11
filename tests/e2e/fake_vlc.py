"""A stand-in for VLC 3 in the end-to-end test: answers on 127.0.0.1 as VLC's web interface does
while it plays one video, so ReflektorTTS reads the subtitle file next to that video.

The test runs it as a program named like VLC's (programs.start_fake_vlc), since ReflektorTTS
finds VLC by that name. It uses only the standard library: it may run without the project's
packages. Arguments: the port, the web interface's password and the video's path.
"""

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ITEM = 4
"""The playlist ID of the video, as VLC numbers it: its first item after a start."""
LENGTH = 600
"""The video's length in seconds; it stays at second 1, inside the test's one subtitle."""


def answers(media: Path) -> dict[str, Any]:
    """VLC 3's answers to the two requests ReflektorTTS sends, with only the fields it reads and a few more."""
    status = {
        "apiversion": 3,
        "version": "3.0.21 Vetinari",
        "state": "playing",
        "time": 1,
        "position": 1 / LENGTH,
        "length": LENGTH,
        "rate": 1.0,
        "subtitledelay": 0,
        "currentplid": ITEM,
    }
    video = {"type": "leaf", "id": str(ITEM), "name": media.name, "uri": media.as_uri(), "duration": LENGTH}
    playlist = {"type": "node", "id": "1", "name": "", "children": [{"type": "node", "id": "2", "children": [video]}]}
    return {"/requests/status.json": status, "/requests/playlist.json": playlist}


def serve(port: int, password: str, media: Path) -> None:
    expected = "Basic " + base64.b64encode(f":{password}".encode()).decode("ascii")
    bodies = {path: json.dumps(answer).encode() for path, answer in answers(media).items()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Authorization") != expected:
                self.send_error(401)
                return
            body = bodies.get(self.path.partition("?")[0])
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            """Quiet: ReflektorTTS asks five times a second."""

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
