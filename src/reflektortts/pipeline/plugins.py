"""Plugin registry: plugins announce themselves through Python entry points."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from importlib.metadata import entry_points
from typing import Any

from reflektortts.games.detector import RunningGame
from reflektortts.pipeline.protocols import Source, Stage
from reflektortts.profiles.model import SourceSettings

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


def load_schema(package: str, file_name: str) -> Mapping[str, Any]:
    """Reads a plugin's JSON Schema shipped as a file in its package."""
    schema: Mapping[str, Any] = json.loads(resources.files(package).joinpath(file_name).read_text("utf-8"))
    return schema


def _load[Plugin: (SourcePlugin, StagePlugin)](group: str, kind: type[Plugin]) -> dict[str, Plugin]:
    plugins: dict[str, Plugin] = {}
    for entry_point in entry_points(group=group):
        plugin = entry_point.load()
        if not isinstance(plugin, kind):
            raise TypeError(f"Entry point {entry_point.value} in {group} is not a {kind.__name__}")
        plugins[plugin.type] = plugin
    return plugins


def source_plugins() -> dict[str, SourcePlugin]:
    return _load(SOURCE_GROUP, SourcePlugin)


def stage_plugins() -> dict[str, StagePlugin]:
    return _load(STAGE_GROUP, StagePlugin)
