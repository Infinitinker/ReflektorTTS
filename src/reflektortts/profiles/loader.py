"""Loads profile files: parses, migrates to the current version and validates them."""

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import jsonschema
from jsonschema.protocols import Validator

from reflektortts.glossary import Glossaries, Glossary, GlossaryTerm
from reflektortts.languages import LanguageError, check_language
from reflektortts.pipeline.plugins import source_plugins, stage_plugins
from reflektortts.profiles.model import (
    ANY_LANGUAGE,
    App,
    Executable,
    Match,
    Profile,
    Rating,
    SourceSettings,
    StageSettings,
)

logger = logging.getLogger(__name__)

CURRENT_VERSION = 2


def _from_version_1(data: dict[str, Any]) -> dict[str, Any]:
    """Version 2 adds tested_languages, which a version 1 profile does not say."""
    return data | {"version": 2}


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _from_version_1}
"""MIGRATIONS[n] turns a version n profile into version n + 1."""

# Fields of source and stage entries the core reads; the rest belong to the plugin.
SOURCE_FIELDS = {"type", "name", "poll_interval_ms", "stages"}
STAGE_FIELDS = {"type", "text", "speech"}
DEFAULT_POLL_INTERVAL_MS = 250


@dataclass(frozen=True)
class PluginSchemas:
    """What loading a profile needs from the installed plugins: their types mapped to the JSON
    Schema of their own fields, and, for sources, to the builds of the app those fields are for."""

    sources: Mapping[str, Mapping[str, Any]]
    stages: Mapping[str, Mapping[str, Any]]
    source_builds: Mapping[str, Callable[[Mapping[str, Any]], Iterable[str]]] = field(default_factory=dict)
    """Source types mapped to their plugin's SourcePlugin.builds."""


class ProfileError(Exception):
    """A profile file cannot be used; the message says which file and why."""


@cache
def _validator() -> jsonschema.Draft202012Validator:
    schema_text = resources.files("reflektortts.profiles").joinpath("profile.schema.json").read_text("utf-8")
    return jsonschema.Draft202012Validator(json.loads(schema_text))


def installed_plugin_schemas() -> PluginSchemas:
    sources = source_plugins()
    return PluginSchemas(
        sources={type_: plugin.settings_schema for type_, plugin in sources.items()},
        stages={type_: plugin.settings_schema for type_, plugin in stage_plugins().items()},
        source_builds={type_: plugin.builds for type_, plugin in sources.items()},
    )


def _migrate(data: dict[str, Any], name: str) -> dict[str, Any]:
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProfileError(f'{name}: "version" must be a whole number.')
    if version < 1:
        raise ProfileError(f'{name}: "version" must be from 1 to {CURRENT_VERSION}.')
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
        # utf-8-sig also reads files that editors saved with a byte order mark.
        data = json.loads(path.read_text("utf-8-sig"))
    except OSError as error:
        raise ProfileError(f"{name}: cannot be read ({error.strerror}).") from error
    except json.JSONDecodeError as error:
        where = f"line {error.lineno}, column {error.colno}"
        raise ProfileError(f"{name}: not valid JSON: {error.msg} ({where}).") from error
    except UnicodeDecodeError as error:
        raise ProfileError(f"{name}: not saved as UTF-8. Save it as UTF-8 in your editor, then reload.") from error
    except RecursionError as error:
        raise ProfileError(f"{name}: nested too deeply to read.") from error
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
    _check_builds(sources, executables, schemas, name)
    return Profile(
        id=profile_id,
        app=App(title=data["app"]["title"], year=data["app"]["year"]),
        match=Match(executables),
        sources=sources,
        overlay=overlay,
        glossary=_glossaries(data.get("glossary", {}), name),
        rating=Rating(data["rating"]) if "rating" in data else None,
        tested_languages=_tested_languages(data.get("tested_languages", []), name),
    )


def _tested_languages(languages: list[str] | str, name: str) -> tuple[str, ...] | Literal["any"]:
    if languages == ANY_LANGUAGE:
        return ANY_LANGUAGE
    for index, language in enumerate(languages):
        _check_language(language, f"{name}: $.tested_languages[{index}]")
    return tuple(languages)


def _glossaries(glossaries: dict[str, list[dict[str, Any]]], name: str) -> Glossaries:
    for language in glossaries:
        _check_language(language, f"{name}: $.glossary.{language}")
    return {language: _glossary(entries, f"{name}: $.glossary.{language}") for language, entries in glossaries.items()}


def _check_language(code: str, where: str) -> None:
    try:
        check_language(code)
    except LanguageError as error:
        raise ProfileError(f"{where}: {error}") from error


def _glossary(entries: list[dict[str, Any]], path: str) -> Glossary:
    """A glossary's terms, each of which must say what to do with it, and only once."""
    terms: list[GlossaryTerm] = []
    for index, entry in enumerate(entries):
        spellings = [entry["term"]] if isinstance(entry["term"], str) else entry["term"]
        term = GlossaryTerm(
            term=spellings[0],
            other_spellings=tuple(spellings[1:]),
            keep=entry.get("keep", False),
            female=entry.get("female", False),
            means=entry.get("means"),
            pronounce=entry.get("pronounce", {}),
        )
        where = f'{path}[{index}] ("{term.term}")'
        for language in term.pronounce:
            _check_language(language, f"{where}.pronounce")
        if not (term.keep or term.means or term.pronounce):
            raise ProfileError(f'{where}: says nothing to do with the term: give it "keep", "means" or "pronounce".')
        if term.keep and term.means:
            raise ProfileError(f'{where}: a term is either kept or given a meaning: remove "keep" or "means".')
        if term.female and not term.keep:
            raise ProfileError(f'{where}: "female" applies only to a kept term: add "keep": true or remove it.')
        seen = [spelling for other in terms for spelling in other.spellings]
        for spelling in term.spellings:
            if spelling in seen:
                raise ProfileError(f'{where}: "{spelling}" is in the glossary twice: keep it in one entry.')
            seen.append(spelling)
        terms.append(term)
    return tuple(terms)


def _check_unique_names(sources: tuple[SourceSettings, ...], name: str) -> None:
    """Sources are switched on and off, and their stages found, by name, so two may not share one."""
    seen: set[str] = set()
    for source in sources:
        if source.name in seen:
            raise ProfileError(f'{name}: two sources are named "{source.name}"; give each its own name.')
        seen.add(source.name)


def _check_builds(
    sources: tuple[SourceSettings, ...], executables: tuple[Executable, ...], schemas: PluginSchemas, name: str
) -> None:
    """In a profile that lists its builds, a source set up for a build of the app, e.g. with a
    pointer chain found in it, must be for a listed one: any other build is never read, so it is
    most likely a typo that leaves a listed build without its source."""
    if not all(executable.sha256 for executable in executables):
        return
    listed = {build for executable in executables for build in executable.sha256}
    for index, source in enumerate(sources):
        hook = schemas.source_builds.get(source.type)
        if hook is None:
            continue
        where = f'{name}: $.sources[{index}] ("{source.name}")'
        for build in _source_builds(hook, source, where):
            if build.lower() not in listed:
                raise ProfileError(
                    f'{where} is set up for the build {build}, which "match" does not list. Add it to the "sha256" '
                    "of its executable, or correct it in the source."
                )


def _source_builds(
    hook: Callable[[Mapping[str, Any]], Iterable[str]], source: SourceSettings, where: str
) -> tuple[str, ...]:
    """The plugin's builds hook, which must not stop profile loading: if it fails or returns
    something other than strings, the profile is refused and the failure is logged."""
    try:
        builds = tuple(hook(source.settings))
        if not all(isinstance(build, str) for build in builds):
            raise TypeError(f"builds must be strings, got {builds!r}")
    except Exception as error:
        logger.exception("The %s source plugin cannot tell which builds %s is for", source.type, where)
        raise ProfileError(
            f"{where}: the {source.type} source plugin cannot tell which builds it is for ({error})."
        ) from error
    return builds
