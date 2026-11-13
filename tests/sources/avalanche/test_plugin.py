"""Registering the avalanche source through its entry point."""

from reflektortts.pipeline.plugins import source_plugins
from reflektortts.sources.avalanche.plugin import PLUGIN


def test_avalanche_plugin_is_registered_through_entry_points() -> None:
    assert source_plugins()["avalanche"] is PLUGIN
