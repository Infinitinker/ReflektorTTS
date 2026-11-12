"""How VLC's web interface is set up in vlcrc: whether it is on, its password, host and port."""

import logging
from dataclasses import dataclass
from pathlib import Path

from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.vlcrc import Vlcrc

logger = logging.getLogger(__name__)

WEB_INTERFACES = frozenset({"http", "luahttp"})
"""The names VLC knows its web interface by in its module lists."""
INTERFACE_LISTS = ("extraintf", "control", "intf")
"""The settings that name the interfaces VLC starts: any of them may hold the web interface."""
DEFAULT_PORT = 8080
REACHABLE_HOSTS = frozenset({"", "0.0.0.0", "127.0.0.1", "localhost"})
"""Values of http-host with which the web interface answers on 127.0.0.1 (empty: on every
network interface)."""

NOT_FOUND = "VLC’s settings file was not found: if VLC is installed, start it once, close it, and try again."


@dataclass(frozen=True)
class WebSettings:
    interface_on: bool
    password: bytes
    host: str
    port: int

    @property
    def ready(self) -> bool:
        """Whether VLC starts the web interface: VLC 3 turns it off without a password."""
        return self.interface_on and bool(self.password)


def web_settings(rc: Vlcrc) -> WebSettings:
    return WebSettings(
        interface_on=any(entry in WEB_INTERFACES for key in INTERFACE_LISTS for entry in rc.values(key)),
        password=rc.value("http-password") or b"",
        host=(rc.value("http-host") or b"").decode("ascii", errors="replace").strip(),
        port=_port(rc.value("http-port")),
    )


def _port(value: bytes | None) -> int:
    """VLC's port: it reads the number as C does (e.g. "0x1F90" too), and ignores one out of range."""
    try:
        port = int((value or b"").decode("ascii"), 0)
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


class SettingsFile:
    """Reads the web interface's settings from vlcrc again whenever the file changes.

    VLC saves vlcrc by deleting it and renaming a new file in its place, so for a moment it is
    missing; the last settings read are kept meanwhile."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._settings: WebSettings | None = None

    def current(self) -> WebSettings:
        """Raises VlcError if the file has never been read."""
        try:
            stat = self._path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._stamp and self._settings is not None:
                return self._settings
            settings = web_settings(Vlcrc(self._path.read_bytes()))
        except OSError as error:
            if self._settings is not None:
                logger.debug("Keeping VLC's web interface settings read before: %s", error)
                return self._settings
            if isinstance(error, FileNotFoundError):
                raise VlcError(NOT_FOUND) from error
            raise VlcError(f"Cannot read VLC’s settings file ({error.strerror}): {self._path}.") from error
        self._settings, self._stamp = settings, stamp
        return settings
