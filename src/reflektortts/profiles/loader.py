"""Loads profile files: parses, migrates to the current version and validates them."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.protocols import Validator

from reflektortts.glossary import Glossary, GlossaryTerm
from reflektortts.pipeline.plugins import source_plugins, stage_plugins
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings, StageSettings

CURRENT_VERSION = 1

# MIGRATIONS[n] turns a version n profile into version n + 1. Empty until the format changes after
# the first release.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}

# Fields of source and stage entries the core reads; the rest belong to the plugin.
SOURCE_FIELDS = {"type", "name", "poll_interval_ms", "stages"}
STAGE_FIELDS = {"type", "text", "speech"}
DEFAULT_POLL_INTERVAL_MS = 250


@dataclass(frozen=True)
class PluginSchemas:
    """Plugin types mapped to the JSON Schema of their own fields."""

    sources: Mapping[str, Mapping[str, Any]]
    stages: Mapping[str, Mapping[str, Any]]


class ProfileError(Exception):
    """A profile file cannot be used; the message says which file and why."""


@cache
def _validator() -> jsonschema.Draft202012Validator:
    schema_text = resources.files("reflektortts.profiles").joinpath("profile.schema.json").read_text("utf-8")
    return jsonschema.Draft202012Validator(json.loads(schema_text))


def installed_plugin_schemas() -> PluginSchemas:
    return PluginSchemas(
        sources={type_: plugin.settings_schema for type_, plugin in source_plugins().items()},
        stages={type_: plugin.settings_schema for type_, plugin in stage_plugins().items()},
    )


def _migrate(data: dict[str, Any], name: str) -> dict[str, Any]:
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProfileError(f'{name}: "version" must be a whole number.')
    if version > CURRENT_VERSION:
        raise ProfileError(f"{name}: made for a newer ReflektorTTS (profile version {version}). Update ReflektorTTS.")
    while version < CURRENT_VERSION:
        data = MIGRATIONS[version](data)
        version = data["version"]
    return data


def _check(validator: Validator, data: Any, name: str, path: str = "$") -> None:
    problem = jsonschema.exceptions.best_match(validator.iter_errors(data))
    if problem is not None:
        raise ProfileError(f"{name}: {path}{problem.json_path[1:]}: {problem.message}")


def _plugin_settings(
    entry: Mapping[str, Any], core_fields: set[str], schemas: Mapping[str, Mapping[str, Any]], kind: str, path: str
) -> dict[str, Any]:
    """Validates an entry's plugin fields against its plugin's schema and returns them."""
    schema = schemas.get(entry["type"])
    if schema is None:
        installed = ", ".join(sorted(schemas)) or "none"
        raise ProfileError(f'{path}: unknown {kind} type "{entry["type"]}" (installed: {installed}).')
    settings = {key: value for key, value in entry.items() if key not in core_fields}
    # Format checks catch e.g. invalid regular expressions while the profile loads.
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    problem = jsonschema.exceptions.best_match(validator.iter_errors(settings))
    if problem is not None:
        raise ProfileError(f"{path}{problem.json_path[1:]}: {problem.message}")
    return settings


def _source(entry: Mapping[str, Any], index: int, schemas: PluginSchemas, name: str) -> SourceSettings:
    path = f"{name}: $.sources[{index}]"
    return SourceSettings(
        type=entry["type"],
        name=entry["name"],
        poll_interval=entry.get("poll_interval_ms", DEFAULT_POLL_INTERVAL_MS) / 1000,
        settings=_plugin_settings(entry, SOURCE_FIELDS, schemas.sources, "source", path),
        stages=tuple(
            StageSettings(
                type=stage["type"],
                settings=_plugin_settings(stage, STAGE_FIELDS, schemas.stages, "stage", f"{path}.stages[{position}]"),
                text=stage.get("text", True),
                speech=stage.get("speech", True),
            )
            for position, stage in enumerate(entry.get("stages", []))
        ),
    )


def load_profile(path: Path, schemas: PluginSchemas | None = None) -> Profile:
    """schemas defaults to the installed plugins' schemas."""
    name = path.name
    try:
        data = json.loads(path.read_text("utf-8"))
    except OSError as error:
        raise ProfileError(f"{name}: cannot be read ({error.strerror}).") from error
    except json.JSONDecodeError as error:
        raise ProfileError(f"{name}: not valid JSON (line {error.lineno}, column {error.colno}).") from error
    return parse_profile(data, path.stem, schemas)


def parse_profile(data: Any, profile_id: str, schemas: PluginSchemas | None = None) -> Profile:
    """Checks and reads a profile's JSON data, as in the file <profile_id>.json; raises
    ProfileError naming that file and the problem."""
    name = f"{profile_id}.json"
    if not isinstance(data, dict):
        raise ProfileError(f"{name}: must contain a JSON object.")

    data = _migrate(data, name)
    _check(_validator(), data, name)
    schemas = installed_plugin_schemas() if schemas is None else schemas
    sources = tuple(_source(entry, index, schemas, name) for index, entry in enumerate(data.get("sources", [])))
    _check_unique_names(sources, name)
    executables = tuple(
        Executable(entry["name"], tuple(entry.get("sha256", ()))) for entry in data["match"]["executables"]
    )
    overlay = bool(data.get("overlay", False))
    if overlay and not all(executable.sha256 for executable in executables):
        raise ProfileError(
            f'{name}: "overlay" needs the "sha256" of every executable, so the overlay is loaded only into '
            "builds it was tested with."
        )
    return Profile(
        id=profile_id,
        app=App(title=data["app"]["title"], year=data["app"]["year"]),
        match=Match(executables),
        sources=sources,
        overlay=overlay,
        glossary=_glossary(data.get("glossary", []), name),
    )


def _glossary(entries: list[dict[str, Any]], name: str) -> Glossary:
    """The glossary's terms, each of which must say what to do with it, and only once."""
    terms: list[GlossaryTerm] = []
    for index, entry in enumerate(entries):
        term = GlossaryTerm(
            term=entry["term"],
            keep=entry.get("keep", False),
            female=entry.get("female", False),
            means=entry.get("means"),
            say=entry.get("say", {}),
        )
        where = f'{name}: $.glossary[{index}] ("{term.term}")'
        if not (term.keep or term.means or term.say):
            raise ProfileError(f'{where}: says nothing to do with the term; give it "keep", "means" or "say".')
        if term.keep and term.means:
            raise ProfileError(f'{where}: a term is either kept or given a meaning; remove "keep" or "means".')
        if term.female and not term.keep:
            raise ProfileError(f'{where}: "female" applies only to a kept term; add "keep": true or remove it.')
        if any(term.term == other.term for other in terms):
            raise ProfileError(f"{where}: the term is in the glossary twice; merge the two entries.")
        terms.append(term)
    return tuple(terms)


def _check_unique_names(sources: tuple[SourceSettings, ...], name: str) -> None:
    """Sources are switched on and off, and their stages found, by name, so two may not share one."""
    seen: set[str] = set()
    for source in sources:
        if source.name in seen:
            raise ProfileError(f'{name}: two sources are named "{source.name}"; give each its own name.')
        seen.add(source.name)
