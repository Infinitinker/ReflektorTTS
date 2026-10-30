"""Loads profile files: parses, migrates to the current version and validates them."""

import json
from collections.abc import Callable
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from reflektortts.profiles.model import Game, Match, Profile

CURRENT_VERSION = 1

# MIGRATIONS[n] turns a version n profile into version n + 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ProfileError(Exception):
    """A profile file cannot be used; the message says which file and why."""


@cache
def _validator() -> jsonschema.Draft202012Validator:
    schema_text = resources.files("reflektortts.profiles").joinpath("profile.schema.json").read_text("utf-8")
    return jsonschema.Draft202012Validator(json.loads(schema_text))


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


def load_profile(path: Path) -> Profile:
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
    problem = jsonschema.exceptions.best_match(_validator().iter_errors(data))
    if problem is not None:
        raise ProfileError(f"{name}: {problem.json_path}: {problem.message}")

    return Profile(
        id=path.stem,
        game=Game(title=data["game"]["title"], year=data["game"]["year"]),
        match=Match(processes=tuple(data["match"]["process"])),
    )


def load_profiles(directory: Path) -> tuple[list[Profile], list[ProfileError]]:
    """Loads every *.json profile in directory; a broken one is reported, not fatal."""
    profiles: list[Profile] = []
    errors: list[ProfileError] = []
    for path in sorted(directory.glob("*.json")):
        try:
            profiles.append(load_profile(path))
        except ProfileError as error:
            errors.append(error)
    return profiles, errors
