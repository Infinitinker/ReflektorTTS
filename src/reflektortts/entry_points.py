"""Finds plugins: every plugin announces itself through a Python entry point in its group."""

import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)


def load_plugins[Plugin](group: str, kind: type[Plugin]) -> list[Plugin]:
    """Every plugin in the group. One that cannot be imported, or is not a kind, is logged and
    skipped, so a broken plugin cannot stop the others or the app."""
    plugins = []
    for entry_point in entry_points(group=group):
        try:
            plugin = entry_point.load()
        except Exception:
            logger.exception("The plugin %s in %s cannot be loaded; skipping it", entry_point.value, group)
            continue
        if not isinstance(plugin, kind):
            logger.error("The plugin %s in %s is not a %s; skipping it", entry_point.value, group, kind.__name__)
            continue
        plugins.append(plugin)
    return plugins
