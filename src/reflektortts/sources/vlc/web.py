"""A client of VLC 3's web interface on 127.0.0.1: what VLC plays, and where it is."""

import base64
import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from reflektortts.sources.vlc.errors import VlcError

API_VERSION = 3
"""The version of the web interface this client reads (VLC 3); VLC 4's has not been checked."""
TIMEOUT = 0.5
"""Seconds to wait for an answer; on 127.0.0.1, VLC answers in a few milliseconds."""

OpenUrl = Callable[[urllib.request.Request, float], bytes]
"""Sends a request with a timeout in seconds and returns the body of the answer; raises as urllib does."""

_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
"""Never through a proxy: the system's proxy settings must not apply to 127.0.0.1."""


def open_local(request: urllib.request.Request, timeout: float) -> bytes:
    with _local.open(request, timeout=timeout) as response:
        body: bytes = response.read()
        return body


class NotAnsweringError(VlcError):
    """Nothing answers on VLC's port: VLC is starting, or its web interface did not start."""


@dataclass(frozen=True)
class PlayerStatus:
    state: str
    """"playing", "paused" or "stopped"."""
    time: int
    """Where playback is in the media, in whole seconds (rounded down)."""
    position: float
    """Where playback is, as a fraction of the media's length."""
    length: int
    """The media's length in whole seconds (rounded down); 0 or less if unknown."""
    rate: float
    """Playback speed: 1 is normal."""
    subtitle_delay: float
    """Seconds subtitles are shown later than their files say (earlier if negative)."""
    item: int
    """The playlist ID of the media playing; -1 if none."""


@dataclass(frozen=True)
class PlaylistItem:
    name: str
    uri: str


class VlcClient:
    def __init__(self, port: int, password: bytes, open_url: OpenUrl = open_local) -> None:
        self._base = f"http://127.0.0.1:{port}"
        self._port = port
        self._authorization = "Basic " + base64.b64encode(b":" + password).decode("ascii")
        self._open_url = open_url

    def status(self) -> PlayerStatus:
        return parse_status(self._get("/requests/status.json"), self._port)

    def playlist_item(self, item: int) -> PlaylistItem | None:
        """The playlist's item with that ID, or None if it is not in the playlist."""
        return find_item(self._get("/requests/playlist.json"), str(item))

    def _get(self, path: str) -> Any:
        # Asked without commands: an answer to a command is the status from before it took effect.
        request = urllib.request.Request(self._base + path, headers={"Authorization": self._authorization})
        try:
            body = self._open_url(request, TIMEOUT)
        except urllib.error.HTTPError as error:
            raise _refused(error.code, self._port) from error
        except (OSError, http.client.HTTPException) as error:
            raise NotAnsweringError(
                f"VLC's web interface does not answer on port {self._port}: restart VLC. "
                "If that does not help, another program may be using the port: "
                "give VLC's web interface another port in VLC's preferences."
            ) from error
        try:
            return json.loads(body)
        except ValueError as error:
            raise _not_vlc(self._port) from error


def _refused(code: int, port: int) -> VlcError:
    if code == 401:
        return VlcError("VLC did not accept the web interface password: close VLC and start it again.")
    if code in (403, 404):
        # VLC 3 turns its web interface off, answering 403 and 404, if it started without a password.
        return VlcError("The VLC that is running has its web interface off: close VLC and start it again.")
    return VlcError(f"VLC's web interface on 127.0.0.1:{port} answered with an error (HTTP {code}).")


def _not_vlc(port: int) -> VlcError:
    return VlcError(
        f"Another program answers on port {port}, not VLC: give VLC's web interface another port "
        "in VLC's preferences, then restart VLC."
    )


def parse_status(data: Any, port: int) -> PlayerStatus:
    """Raises VlcError for an answer that is not VLC 3's status."""
    if not isinstance(data, Mapping) or not isinstance(data.get("apiversion"), int):
        raise _not_vlc(port)
    if data["apiversion"] != API_VERSION:
        version = data.get("version")
        raise VlcError(
            f"This VLC version ({version if isinstance(version, str) else 'unknown'}) is not supported yet: "
            "VLC 3 is."
        )
    try:
        status = PlayerStatus(
            state=_field(data, "state", str),
            time=int(_number(data, "time")),
            position=_number(data, "position"),
            length=int(_number(data, "length")),
            rate=_number(data, "rate"),
            subtitle_delay=_number(data, "subtitledelay"),
            item=int(_number(data, "currentplid")),
        )
    except (KeyError, TypeError) as error:
        raise _not_vlc(port) from error
    return status


def _field[T](data: Mapping[str, Any], key: str, kind: type[T]) -> T:
    value = data[key]
    if not isinstance(value, kind):
        raise TypeError(f"{key} is not a {kind.__name__}")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} is not a number")
    return float(value)


def find_item(node: Any, item: str) -> PlaylistItem | None:
    """The leaf of the playlist tree with that ID: IDs are strings there."""
    if not isinstance(node, Mapping):
        return None
    if node.get("type") == "leaf" and str(node.get("id")) == item:
        name, uri = node.get("name"), node.get("uri")
        return PlaylistItem(name if isinstance(name, str) else "", uri) if isinstance(uri, str) else None
    children = node.get("children")
    if not isinstance(children, list):
        return None
    return next((found for child in children if (found := find_item(child, item)) is not None), None)
