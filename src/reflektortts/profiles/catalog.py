"""Every profile ReflektorTTS knows: the bundled ones and the user's own, and which of them are
used.

Bundled profiles ship with ReflektorTTS and are replaced with each update; the user's own are in
their profiles folder. A user profile with a bundled profile's ID (its file name) replaces it. Of
two profiles that match the same build of an app, the user's own is used; two of the user's own
clash, and neither is used until one is disabled.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from reflektortts.profiles.loader import PluginSchemas, ProfileError, installed_plugin_schemas, load_profile
from reflektortts.profiles.model import Profile

BUNDLED_DIR = Path(__file__).parent / "bundled"


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
