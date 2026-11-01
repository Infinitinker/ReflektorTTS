"""Every profile ReflektorTTS knows: the bundled ones and the user's own, and which of them are
used.

Bundled profiles ship with ReflektorTTS and are replaced with each update; the user's own are in
their profiles folder. A user profile with a bundled profile's ID (its file name) replaces it. Of
two profiles that match the same build of an app, the user's own is used; two of the user's own
clash, and neither is used until one is disabled.
"""

import json
import os
import re
import shutil
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from reflektortts.profiles.loader import (
    PluginSchemas,
    ProfileError,
    installed_plugin_schemas,
    load_profile,
    parse_profile,
)
from reflektortts.profiles.model import Profile

BUNDLED_DIR = Path(__file__).parent / "bundled"
PROFILE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
"""What a profile's ID, its file name without .json, may be: e.g. "grand-theft-auto-2-1999"."""


class ProfileChangeError(Exception):
    """A profile cannot be added, copied or removed; the message says why."""


class ProfileExistsError(ProfileChangeError):
    """The user already has a profile with that ID."""


class Origin(StrEnum):
    BUNDLED = "bundled"
    CUSTOM = "custom"
    """The user's own profile."""
    OVERRIDE = "override"
    """The user's own profile, with a bundled profile's ID: it replaces that one."""


class Standing(StrEnum):
    """Whether a profile is used, apart from whether its app is running."""

    USED = "used"
    DISABLED = "disabled"
    NOT_USED = "not_used"
    """Another profile, the user's own, matches the same build of the app."""
    CLASH = "clash"
    """Another of the user's own profiles matches the same build of the app."""
    BROKEN = "broken"
    """The file cannot be read as a profile."""


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    """The file name without .json."""
    origin: Origin
    path: Path
    profile: Profile | None
    """None if the file is broken; error says why."""
    error: str | None = None


class ProfileState(StrEnum):
    """A profile as the user sees it: why it is not used, or what its app is doing."""

    READING = "reading"
    NOT_RUNNING = "not_running"
    UNSUPPORTED = "unsupported"
    """Its app runs, in a build the profile does not list."""
    DISABLED = "disabled"
    NOT_USED = "not_used"
    CLASH = "clash"
    BROKEN = "broken"


@dataclass(frozen=True)
class Choice:
    entry: CatalogEntry
    standing: Standing
    reason: str | None = None
    """Why the profile is not used, for the user; None if it is, or is disabled."""


def load_catalog(
    user_dir: Path, bundled_dir: Path = BUNDLED_DIR, schemas: PluginSchemas | None = None
) -> list[CatalogEntry]:
    """Every profile file in both folders, by ID; a user file replaces a bundled one with its ID,
    even if it is broken, so the user sees what is wrong with their own."""
    schemas = installed_plugin_schemas() if schemas is None else schemas
    bundled = {path.stem: path for path in _files(bundled_dir)}
    user = {path.stem: path for path in _files(user_dir)}
    entries = []
    for profile_id in sorted(bundled.keys() | user.keys()):
        if profile_id in user:
            origin = Origin.OVERRIDE if profile_id in bundled else Origin.CUSTOM
            entries.append(_load(profile_id, origin, user[profile_id], schemas))
        else:
            entries.append(_load(profile_id, Origin.BUNDLED, bundled[profile_id], schemas))
    return entries


class ProfileFiles(Protocol):
    """Where the core reads profiles from and changes the user's own; see ProfileStore."""

    def load(self) -> list[CatalogEntry]: ...

    def add(self, profile_id: str, data: Any, replace: bool) -> Path: ...

    def copy(self, profile_id: str) -> Path: ...

    def remove(self, profile_id: str) -> None: ...


class ProfileStore:
    """The bundled profiles and the user's own folder: reads them, and adds, copies and removes
    the user's own files. Bundled files are never changed."""

    def __init__(self, user_dir: Path, bundled_dir: Path = BUNDLED_DIR, schemas: PluginSchemas | None = None) -> None:
        self.user_dir = user_dir
        self._bundled_dir = bundled_dir
        self._schemas = installed_plugin_schemas() if schemas is None else schemas

    def load(self) -> list[CatalogEntry]:
        return load_catalog(self.user_dir, self._bundled_dir, self._schemas)

    def add(self, profile_id: str, data: Any, replace: bool) -> Path:
        """Saves a profile to the user's folder once it is checked; a broken one raises
        ProfileError and nothing is written."""
        if not PROFILE_ID.fullmatch(profile_id):
            raise ProfileChangeError(
                f'"{profile_id}" cannot be the name of a profile: use lowercase letters, digits and '
                'hyphens, e.g. "grand-theft-auto-2-1999". Rename the file and import it again.'
            )
        parse_profile(data, profile_id, self._schemas)
        path = self._user_path(profile_id)
        if path.exists() and not replace:
            raise ProfileExistsError(f"You already have a profile named {path.name}.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        os.replace(temporary, path)
        return path

    def copy(self, profile_id: str) -> Path:
        """Copies a bundled profile to the user's folder, where it replaces the bundled one."""
        bundled = self._bundled_dir / f"{profile_id}.json"
        if not bundled.is_file():
            raise ProfileChangeError(f"{profile_id}.json is not a bundled profile, so there is nothing to copy.")
        path = self._user_path(profile_id)
        if path.exists():
            raise ProfileExistsError(f"You already have your own {path.name}: edit that one.")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, path)
        return path

    def remove(self, profile_id: str) -> None:
        """Deletes the user's own file; a bundled profile with its ID is then used again."""
        path = self._user_path(profile_id)
        if not path.is_file():
            raise ProfileChangeError(f"{path.name} is a bundled profile, which cannot be removed: disable it instead.")
        path.unlink()

    def _user_path(self, profile_id: str) -> Path:
        return self.user_dir / f"{profile_id}.json"


def choose(catalog: list[CatalogEntry], disabled: Collection[str]) -> list[Choice]:
    """Which profiles are used, in catalog order: every profile not disabled, broken or
    matching an app another one is used for."""
    standings: dict[str, Choice] = {}
    for entry in catalog:
        if entry.profile is None:
            standings[entry.id] = Choice(entry, Standing.BROKEN, entry.error)
        elif entry.id in disabled:
            standings[entry.id] = Choice(entry, Standing.DISABLED)
    active = [entry for entry in catalog if entry.id not in standings]
    for entry in active:
        if entry.origin != Origin.BUNDLED:
            continue
        for own in active:
            executable = own.origin != Origin.BUNDLED and _shared_executable(entry, own)
            if executable:
                reason = f"{_name(own)} is used instead: both match {executable}."
                standings[entry.id] = Choice(entry, Standing.NOT_USED, reason)
                break
    remaining = [entry for entry in active if entry.id not in standings]
    for entry in remaining:
        for other in remaining:
            executable = other is not entry and _shared_executable(entry, other)
            if executable:
                reason = f"Clashes with {_name(other)}: both match {executable}. Disable one."
                standings[entry.id] = Choice(entry, Standing.CLASH, reason)
                break
    return [standings.get(entry.id, Choice(entry, Standing.USED)) for entry in catalog]


@dataclass(frozen=True)
class ProfileView:
    """A profile with its state, as the API shows it."""

    choice: Choice
    state: ProfileState


def _shared_executable(first: CatalogEntry, second: CatalogEntry) -> str | None:
    """The executable both profiles match a build of: the same name, and a build in both (a
    profile listing no builds matches every one)."""
    assert first.profile is not None and second.profile is not None
    for one in first.profile.match.executables:
        for other in second.profile.match.executables:
            if one.name.lower() != other.name.lower():
                continue
            if not one.sha256 or not other.sha256 or set(one.sha256) & set(other.sha256):
                return one.name
    return None


def _name(entry: CatalogEntry) -> str:
    title = entry.profile.app.title if entry.profile is not None else entry.id
    return f"{title} ({entry.path.name})"


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def _load(profile_id: str, origin: Origin, path: Path, schemas: PluginSchemas) -> CatalogEntry:
    try:
        return CatalogEntry(profile_id, origin, path, load_profile(path, schemas))
    except ProfileError as error:
        return CatalogEntry(profile_id, origin, path, None, str(error))
