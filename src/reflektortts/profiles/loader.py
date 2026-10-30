"""Loads profile files: parses, migrates to the current version and validates them."""

import json
from collections.abc import Callable, Mapping
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.protocols import Validator

from reflektortts.pipeline.plugins import source_plugins
from reflektortts.profiles.model import Game, Match, Profile, SourceSettings

CURRENT_VERSION = 2

# MIGRATIONS[n] turns a version n profile into version n + 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # Version 2 added the optional "sources" list.
    1: lambda data: data | {"version": 2},
}

# Fields of a source entry the core reads; the rest belong to the source's plugin.
SOURCE_FIELDS = {"type", "name", "poll_interval_ms"}
DEFAULT_POLL_INTERVAL_MS = 250

# A source plugin's type mapped to the JSON Schema of its own fields.
SourceSchemas = Mapping[str, Mapping[str, Any]]


class ProfileError(Exception):
    """A profile file cannot be used; the message says which file and why."""


@cache
def _validator() -> jsonschema.Draft202012Validator:
    schema_text = resources.files("reflektortts.profiles").joinpath("profile.schema.json").read_text("utf-8")
    return jsonschema.Draft202012Validator(json.loads(schema_text))


def installed_source_schemas() -> dict[str, Mapping[str, Any]]:
    return {type_: plugin.settings_schema for type_, plugin in source_plugins().items()}


def _migrate(data: dict[str, Any], name: str) -> dict[str, Any]:
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProfileError(f'{name}: "version" must be a whole number.')
    if version > CURRENT_VERSION:
        raise ProfileError(f"{name}: made for a newer ReflektorTTS (profile version {version}). Update the app.")
    while version < CURRENT_VERSION:
        data = MIGRATIONS[version](data)
        version = data["version"]
    return data


def _check(validator: Validator, data: Any, name: str, path: str = "$") -> None:
    problem = jsonschema.exceptions.best_match(validator.iter_errors(data))
    if problem is not None:
        raise ProfileError(f"{name}: {path}{problem.json_path[1:]}: {problem.message}")


def _source(entry: dict[str, Any], index: int, schemas: SourceSchemas, name: str) -> SourceSettings:
    schema = schemas.get(entry["type"])
    if schema is None:
        installed = ", ".join(sorted(schemas)) or "none"
        raise ProfileError(
            f'{name}: $.sources[{index}]: unknown source type "{entry["type"]}" (installed: {installed}).'
        )
    settings = {key: value for key, value in entry.items() if key not in SOURCE_FIELDS}
    _check(jsonschema.Draft202012Validator(schema), settings, name, f"$.sources[{index}]")
    return SourceSettings(
        type=entry["type"],
        name=entry["name"],
        poll_interval=entry.get("poll_interval_ms", DEFAULT_POLL_INTERVAL_MS) / 1000,
        settings=settings,
    )


def load_profile(path: Path, source_schemas: SourceSchemas | None = None) -> Profile:
    """source_schemas defaults to the installed source plugins' schemas."""
    name = path.name
    try:
        data = json.loads(path.read_text("utf-8"))
    except OSError as error:
        raise ProfileError(f"{name}: cannot be read ({error.strerror}).") from error
    except json.JSONDecodeError as error:
        raise ProfileError(f"{name}: not valid JSON (line {error.lineno}, column {error.colno}).") from error
    if not isinstance(data, dict):
        raise ProfileError(f"{name}: must contain a JSON object.")

    data = _migrate(data, name)
    _check(_validator(), data, name)
    schemas = installed_source_schemas() if source_schemas is None else source_schemas
    return Profile(
        id=path.stem,
        game=Game(title=data["game"]["title"], year=data["game"]["year"]),
        match=Match(processes=tuple(data["match"]["process"])),
        sources=tuple(_source(entry, index, schemas, name) for index, entry in enumerate(data.get("sources", []))),
    )


def load_profiles(
    directory: Path, source_schemas: SourceSchemas | None = None
) -> tuple[list[Profile], list[ProfileError]]:
    """Loads every *.json profile in directory; a broken one is reported, not fatal."""
    schemas = installed_source_schemas() if source_schemas is None else source_schemas
    profiles: list[Profile] = []
    errors: list[ProfileError] = []
    for path in sorted(directory.glob("*.json")):
        try:
            profiles.append(load_profile(path, schemas))
        except ProfileError as error:
            errors.append(error)
    return profiles, errors
