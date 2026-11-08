"""The VLC integration: turns VLC's web interface on, for this computer only, and puts back what it
changed.

It changes vlcrc only while VLC is closed: a running VLC writes back the settings it started with
when it closes or saves its preferences. What it changed is recorded in its own state file, since
VLC drops comments when it rewrites vlcrc; the password is not recorded, only its SHA-256.
"""

import contextlib
import hashlib
import json
import logging
import os
import secrets
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from reflektortts.apps.detector import ProcessInfo, running_processes
from reflektortts.integrations import IntegrationError, IntegrationState, IntegrationStatus
from reflektortts.settings import write_json_object
from reflektortts.sources.vlc.vlcrc import Vlcrc
from reflektortts.sources.vlc.web_settings import NOT_FOUND, web_settings

logger = logging.getLogger(__name__)

NAME = "VLC integration"
DESCRIPTION = (
    "Turns on VLC's web interface for this computer only, with a random password kept in VLC's settings, "
    "so ReflektorTTS can follow what VLC plays; any program on this computer that knows the password can "
    "control VLC. Disable puts back the VLC settings ReflektorTTS changed. VLC must be closed for both."
)

VLC_PROCESSES = frozenset({"vlc.exe", "vlc"})
WEB_INTERFACE = "http"
LOOPBACK = "127.0.0.1"
LOCAL_HOSTS = frozenset({LOOPBACK, "localhost"})
"""Values of http-host with which the web interface answers only on this computer."""
INTERFACES = "extraintf"
HOST = "http-host"
PASSWORD = "http-password"

CLOSE_VLC = "Close VLC first, then try again: VLC writes back its own settings when it closes."
TURN_OFF_IN_VLC = "Tools > Preferences, Show settings: All, then Interface > Main interfaces: clear Web"
NOT_OURS = f"VLC's web interface was turned on in VLC, not by ReflektorTTS: turn it off in VLC ({TURN_OFF_IN_VLC})."


class DamagedRecordsError(Exception):
    """The state file exists, but holds no record ReflektorTTS can use; the message says why."""


def new_password() -> str:
    return secrets.token_urlsafe(18)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _line(text: str | None) -> bytes | None:
    """A recorded line as bytes again, exactly as it was in vlcrc."""
    return None if text is None else text.encode("utf-8", errors="surrogateescape")


def _text(line: bytes | None) -> str | None:
    """A vlcrc line as text that JSON can hold, whatever its encoding."""
    return None if line is None else line.decode("utf-8", errors="surrogateescape")


@dataclass(frozen=True)
class Change:
    """A setting the integration changed in vlcrc."""

    original: str | None
    """The line it replaced, without its ending, or None if it added a line."""
    written: str
    """For extraintf, the module it added to the list; for http-password, the SHA-256 of the
    password it wrote; otherwise the value it wrote."""


class VlcIntegration:
    name = NAME
    description = DESCRIPTION

    def __init__(
        self,
        state_file: Path,
        vlcrc: Path,
        list_processes: Callable[[], Iterable[ProcessInfo]] = running_processes,
        password: Callable[[], str] = new_password,
    ) -> None:
        self._state_file = state_file
        self._vlcrc = vlcrc
        self._list_processes = list_processes
        self._password = password

    def state(self) -> IntegrationState:
        try:
            rc = Vlcrc(self._vlcrc.read_bytes())
        except FileNotFoundError:
            return IntegrationState(IntegrationStatus.UNAVAILABLE, NOT_FOUND)
        except OSError as error:
            return IntegrationState(IntegrationStatus.UNAVAILABLE, self._unreadable(error))
        if web_settings(rc).ready:
            return IntegrationState(IntegrationStatus.ENABLED)
        return IntegrationState(IntegrationStatus.DISABLED)

    def enable(self) -> None:
        """Changes only what VLC needs: adds the web interface to extraintf, sets a password if
        there is none, and limits the interface to this computer, also if it was set to listen on
        the network before. A web interface the user set up, which works, is left as it is."""
        self._check_closed()
        rc = self._read()
        settings = web_settings(rc)
        if settings.ready:
            return
        changes: dict[str, Change] = {}
        if not settings.interface_on:
            interfaces = (rc.value(INTERFACES) or b"").rstrip(b":")
            added = interfaces + b":" + WEB_INTERFACE.encode() if interfaces else WEB_INTERFACE.encode()
            changes[INTERFACES] = Change(_text(rc.set(INTERFACES, added)), WEB_INTERFACE)
        if settings.host.lower() not in LOCAL_HOSTS:
            changes[HOST] = Change(_text(rc.set(HOST, LOOPBACK.encode())), LOOPBACK)
        if not settings.password:
            password = self._password().encode("ascii")
            changes[PASSWORD] = Change(_text(rc.set(PASSWORD, password)), _sha256(password))
        # Recorded first, so a crash cannot leave a change unrecorded; taken back if vlcrc cannot be written.
        try:
            recorded = self._changes()
        except DamagedRecordsError as error:
            logger.warning("Replacing the damaged record of VLC settings in %s: %s", self._state_file, error)
            recorded = {}
        self._save(recorded | changes)
        try:
            self._write(rc)
        except IntegrationError:
            self._save(recorded)
            raise
        logger.info("Turned on VLC's web interface: changed %s in %s", ", ".join(changes), self._vlcrc)

    def disable(self) -> None:
        """Puts back each setting enable changed, unless the user has changed it since."""
        self._check_closed()
        try:
            changes = self._changes()
        except DamagedRecordsError as error:
            if self.state().status is IntegrationStatus.ENABLED:
                raise IntegrationError(
                    f"ReflektorTTS's record of what it changed in VLC's settings is damaged ({error}): "
                    f"{self._state_file}. Turn VLC's web interface off in VLC ({TURN_OFF_IN_VLC})."
                ) from error
            logger.warning("Dropping the damaged record of VLC settings in %s: %s", self._state_file, error)
            self._save({})
            return
        if not changes:
            if self.state().status is IntegrationStatus.ENABLED:
                raise IntegrationError(NOT_OURS)
            return
        try:
            rc = Vlcrc(self._vlcrc.read_bytes())
        except FileNotFoundError:
            logger.info("VLC's settings file is gone, so there is nothing to put back: %s", self._vlcrc)
            self._save({})
            return
        except OSError as error:
            raise IntegrationError(self._unreadable(error)) from error
        for key, change in changes.items():
            _undo(rc, key, change)
        self._write(rc)
        self._save({})
        logger.info("Put back %s in %s", ", ".join(changes), self._vlcrc)

    def _check_closed(self) -> None:
        if any(process.name.lower() in VLC_PROCESSES for process in self._list_processes()):
            raise IntegrationError(CLOSE_VLC)

    def _read(self) -> Vlcrc:
        try:
            return Vlcrc(self._vlcrc.read_bytes())
        except FileNotFoundError as error:
            raise IntegrationError(NOT_FOUND) from error
        except OSError as error:
            raise IntegrationError(self._unreadable(error)) from error

    def _unreadable(self, error: OSError) -> str:
        return f"Cannot read VLC's settings file ({error.strerror}): {self._vlcrc}."

    def _write(self, rc: Vlcrc) -> None:
        """Replaces vlcrc in one step, so VLC never finds half of it. A link (from a dotfile
        manager, say) is followed, not replaced."""
        target = self._vlcrc.resolve()
        if not os.access(target, os.W_OK):
            raise IntegrationError(
                f"VLC's settings file is read-only: {target}. Make it writable (in its Properties), then try again."
            )
        temporary = target.with_name(target.name + ".reflektortts.tmp")
        try:
            temporary.write_bytes(rc.to_bytes())
            shutil.copymode(target, temporary)
            os.replace(temporary, target)
        except OSError as error:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise IntegrationError(
                f"Cannot change VLC's settings file ({error.strerror}): {target}. "
                "Close programs that may be using it, then try again."
            ) from error

    def _changes(self) -> dict[str, Change]:
        """What enable changed, as recorded; none if there is no state file. A broken record among
        usable ones is logged and ignored.

        Raises DamagedRecordsError if the state file cannot be read or has no usable record.
        """
        try:
            text = self._state_file.read_text("utf-8-sig")
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeDecodeError) as error:
            raise DamagedRecordsError(f"it cannot be read: {error}") from error
        try:
            data = json.loads(text)
        except ValueError as error:
            raise DamagedRecordsError("it is not JSON") from error
        records = data.get("changes") if isinstance(data, dict) else None
        if not isinstance(records, Mapping):
            raise DamagedRecordsError("it has no list of changes")
        changes = {}
        for key, record in records.items():
            original = record.get("original") if isinstance(record, Mapping) else None
            written = record.get("written") if isinstance(record, Mapping) else None
            if key in (INTERFACES, HOST, PASSWORD) and isinstance(written, str) and isinstance(original, str | None):
                changes[key] = Change(original, written)
            else:
                logger.warning("Ignoring a broken record of a VLC setting in %s: %s", self._state_file, key)
        if not changes:
            raise DamagedRecordsError("none of its records can be used")
        return changes

    def _save(self, changes: Mapping[str, Change]) -> None:
        try:
            if not changes:
                self._state_file.unlink(missing_ok=True)
                return
            records = {key: {"original": change.original, "written": change.written} for key, change in changes.items()}
            write_json_object(self._state_file, {"changes": records})
        except OSError as error:
            raise IntegrationError(
                f"Cannot save what ReflektorTTS changes in VLC's settings ({error.strerror}): {self._state_file}."
            ) from error


def _undo(rc: Vlcrc, key: str, change: Change) -> None:
    original = _line(change.original)
    current = rc.value(key)
    if current is None:
        return
    if key == INTERFACES:
        _remove_interface(rc, current, change.written.encode(), original)
    elif key == PASSWORD:
        if _sha256(current) == change.written:
            rc.restore(key, original)
    elif current == change.written.encode():
        rc.restore(key, original)


def _remove_interface(rc: Vlcrc, current: bytes, added: bytes, original: bytes | None) -> None:
    """Takes the module added out of the list, if it is still there; the original line comes back
    only if the rest of the list is what it was."""
    entries = current.split(b":")
    found = [i for i, entry in enumerate(entries) if entry.strip().lower() == added]
    if not found:
        return
    del entries[found[-1]]
    rest = b":".join(entries)
    prefix = INTERFACES.encode() + b"="
    original_value = original[len(prefix) :] if original is not None and original.startswith(prefix) else b""
    if rest == original_value:
        rc.restore(INTERFACES, original)
    else:
        rc.set(INTERFACES, rest)
