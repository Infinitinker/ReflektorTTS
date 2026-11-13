"""Plugin registry: plugins announce themselves through Python entry points."""

import json
import logging
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from reflektortts.apps.detector import RunningApp
from reflektortts.entry_points import load_plugins
from reflektortts.glossary import Glossaries
from reflektortts.integrations import Integration
from reflektortts.languages import Languages
from reflektortts.pipeline.protocols import Source, Stage
from reflektortts.profiles.model import SourceSettings

logger = logging.getLogger(__name__)

SOURCE_GROUP = "reflektortts.sources"
STAGE_GROUP = "reflektortts.stages"


@dataclass(frozen=True)
class SourcePlugin:
    """What a source plugin registers under the reflektortts.sources entry-point group."""

    type: str
    """The "type" profiles use to pick this plugin, e.g. "memory"."""
    settings_schema: Mapping[str, Any]
    """JSON Schema for the plugin's own fields in a profile's source entry."""
    create: Callable[[SourceSettings, RunningApp], Source]
    builds: Callable[[Mapping[str, Any]], Iterable[str]] = lambda settings: ()
    """The builds of the app (SHA-256 of its executable) that the source's schema-validated fields
    are for, e.g. one per pointer chain. A profile that lists its builds must list each of these."""
    integration: Callable[[Path], Integration] | None = None
    """Creates the integration the source needs, if any, given the JSON file it may keep its state
    in (the file and its folder may not exist yet). It is called once, when the core starts, and
    must not touch files or the app then: only state, enable and disable may."""


@dataclass(frozen=True)
class StagePlugin:
    """What a stage plugin registers under the reflektortts.stages entry-point group."""

    type: str
    settings_schema: Mapping[str, Any]
    """JSON Schema for the plugin's own fields in a profile's stage entry."""
    create: Callable[[Mapping[str, Any], Glossaries], Stage]
    """Creates a stage from its schema-validated settings and its profile's glossaries."""
    summary: str = ""
    """A few words on what the stage does, capitalized like a sentence without a full stop,
    e.g. "Waits until a line settles"; shown next to its name in the settings panel."""
    warning_when_disabled: str | None = None
    """Shown instead of the summary while the stage is switched off, if reading breaks without it;
    written like the summary."""
    inactive_reason: Callable[[Languages], str | None] = lambda languages: None
    """Why the stage does nothing with the user's languages, written like the summary, e.g.
    "Input and output language are the same"; None if it works with them. Meanwhile the stage is
    skipped, and the settings panel grays it out and shows the reason instead of the summary."""
    speech_rules: Mapping[str, Collection[str]] = field(default_factory=dict)
    """What the stage does only for some output languages, listed for each language in the desktop
    app: a few words naming each rule, written like a label, mapped to the codes of the languages
    that have it, e.g. {"Numbers, dates and units": {"en", "pl"}}. Stages that name the same rule
    share it."""


_failed_checks: set[str] = set()
"""Stage types whose inactive_reason failed, so each failure is logged once, not on every line."""


def inactive_reason(plugin: StagePlugin, languages: Languages) -> str | None:
    """The plugin's inactive_reason, which must not stop reading: if it fails, the stage counts as
    inactive, with the failure as its reason, and the failure is logged."""
    try:
        return plugin.inactive_reason(languages)
    except Exception as error:
        if plugin.type not in _failed_checks:
            _failed_checks.add(plugin.type)
            logger.exception("The %s stage cannot tell whether it works with %s", plugin.type, languages)
        return f"Could not check: {error}"


def speech_rules(plugins: Iterable[StagePlugin]) -> dict[str, tuple[str, ...]]:
    """The speech rules each output language has, by its code, in alphabetical order."""
    rules: dict[str, set[str]] = {}
    for plugin in plugins:
        for rule, languages in plugin.speech_rules.items():
            for language in languages:
                rules.setdefault(language, set()).add(rule)
    return {language: tuple(sorted(names)) for language, names in rules.items()}


def load_schema(package: str, file_name: str) -> Mapping[str, Any]:
    """Reads a plugin's JSON Schema shipped as a file in its package."""
    schema: Mapping[str, Any] = json.loads(resources.files(package).joinpath(file_name).read_text("utf-8"))
    return schema


def _load[Plugin: (SourcePlugin, StagePlugin)](group: str, kind: type[Plugin]) -> dict[str, Plugin]:
    """The group's plugins by type; one whose settings schema is not a valid JSON Schema is logged
    and skipped, so profiles that use it are refused instead of stopping the core. Of two plugins
    with the same type, the first is kept and the other logged and skipped."""
    plugins: dict[str, Plugin] = {}
    for plugin in load_plugins(group, kind):
        try:
            jsonschema.Draft202012Validator.check_schema(plugin.settings_schema)
        except jsonschema.SchemaError as error:
            logger.error("The plugin %s has an invalid settings schema (%s); skipping it", plugin.type, error.message)
            continue
        kept = plugins.get(plugin.type)
        if kept is not None:
            logger.warning(
                "The plugins %s and %s in %s both have the type %s; keeping the first, skipping the second",
                kept.create.__module__,
                plugin.create.__module__,
                group,
                plugin.type,
            )
            continue
        plugins[plugin.type] = plugin
    return plugins


def source_plugins() -> dict[str, SourcePlugin]:
    return _load(SOURCE_GROUP, SourcePlugin)


def stage_plugins() -> dict[str, StagePlugin]:
    return _load(STAGE_GROUP, StagePlugin)
