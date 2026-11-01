"""Plugin registry: plugins announce themselves through Python entry points."""

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from reflektortts.entry_points import load_plugins
from reflektortts.games.detector import RunningGame
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
    create: Callable[[SourceSettings, RunningGame], Source]


@dataclass(frozen=True)
class StagePlugin:
    """What a stage plugin registers under the reflektortts.stages entry-point group."""

    type: str
    settings_schema: Mapping[str, Any]
    """JSON Schema for the plugin's own fields in a profile's stage entry."""
    create: Callable[[Mapping[str, Any]], Stage]
    """Creates a stage from its schema-validated settings."""
    summary: str = ""
    """A few words on what the stage does, capitalized like a sentence without a full stop,
    e.g. "Waits until a line settles"; shown next to its name in the overlay."""
    warning_when_disabled: str | None = None
    """Shown instead of the summary while the stage is switched off, if reading breaks without it;
    written like the summary."""
    inactive_reason: Callable[[Languages], str | None] = lambda languages: None
    """Why the stage does nothing with the player's languages, written like the summary, e.g.
    "Game and output language are the same"; None if it works with them. Meanwhile the stage is
    skipped, and the overlay grays it out and shows the reason instead of the summary."""


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


def load_schema(package: str, file_name: str) -> Mapping[str, Any]:
    """Reads a plugin's JSON Schema shipped as a file in its package."""
    schema: Mapping[str, Any] = json.loads(resources.files(package).joinpath(file_name).read_text("utf-8"))
    return schema


def _load[Plugin: (SourcePlugin, StagePlugin)](group: str, kind: type[Plugin]) -> dict[str, Plugin]:
    return {plugin.type: plugin for plugin in load_plugins(group, kind)}


def source_plugins() -> dict[str, SourcePlugin]:
    return _load(SOURCE_GROUP, SourcePlugin)


def stage_plugins() -> dict[str, StagePlugin]:
    return _load(STAGE_GROUP, StagePlugin)
