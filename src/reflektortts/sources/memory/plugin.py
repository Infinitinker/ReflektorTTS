"""Registers the memory source: its settings schema and how to create it for a running game."""

from collections.abc import Mapping
from typing import Any

from reflektortts.games.detector import RunningGame
from reflektortts.games.executable import executable_sha256
from reflektortts.pipeline.plugins import SourcePlugin, load_schema
from reflektortts.process_memory.memory import open_process_memory
from reflektortts.process_memory.pointer import chain_for, parse_pointer_chains
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.memory.source import MemorySettings, MemorySource


def parse_settings(settings: Mapping[str, Any]) -> MemorySettings:
    """Turns schema-validated profile fields into MemorySettings."""
    return MemorySettings(encoding=settings["encoding"], pointers=parse_pointer_chains(settings["pointers"]))


def create(source: SourceSettings, game: RunningGame) -> MemorySource:
    settings = parse_settings(source.settings)
    chain = chain_for(settings.pointers, executable_sha256(game.process.pid))
    memory = open_process_memory(game.process.pid)
    return MemorySource(source.name, source.poll_interval, settings.encoding, chain, memory)


PLUGIN = SourcePlugin(
    type="memory",
    settings_schema=load_schema("reflektortts.sources.memory", "settings.schema.json"),
    create=create,
)
