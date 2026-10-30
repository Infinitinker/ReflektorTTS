"""Plugin registry: plugins announce themselves through Python entry points."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from reflektortts.games.detector import RunningGame
from reflektortts.pipeline.protocols import Source
from reflektortts.profiles.model import SourceSettings

SOURCE_GROUP = "reflektortts.sources"


@dataclass(frozen=True)
class SourcePlugin:
    """What a source plugin registers under the reflektortts.sources entry-point group."""

    type: str
    """The "type" profiles use to pick this plugin, e.g. "memory"."""
    settings_schema: Mapping[str, Any]
    """JSON Schema for the plugin's own fields in a profile's source entry."""
    create: Callable[[SourceSettings, RunningGame], Source]


def source_plugins() -> dict[str, SourcePlugin]:
    plugins: dict[str, SourcePlugin] = {}
    for entry_point in entry_points(group=SOURCE_GROUP):
        plugin = entry_point.load()
        if not isinstance(plugin, SourcePlugin):
            raise TypeError(f"Entry point {entry_point.value} in {SOURCE_GROUP} is not a SourcePlugin")
        plugins[plugin.type] = plugin
    return plugins
