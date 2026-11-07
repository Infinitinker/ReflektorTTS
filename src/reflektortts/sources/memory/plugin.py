"""Registers the memory source: its settings schema and how to create it for a running app."""

from collections.abc import Iterator, Mapping
from typing import Any

from reflektortts.apps.detector import RunningApp
from reflektortts.apps.executable import executable_sha256
from reflektortts.pipeline.plugins import SourcePlugin, load_schema
from reflektortts.process_memory.memory import open_process_memory
from reflektortts.process_memory.pointer import chain_for, parse_pointer_chains
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.memory.source import MemorySettings, MemorySource


def parse_settings(settings: Mapping[str, Any]) -> MemorySettings:
    """Turns schema-validated profile fields into MemorySettings."""
    return MemorySettings(encoding=settings["encoding"], pointers=parse_pointer_chains(settings["pointers"]))


def builds(settings: Mapping[str, Any]) -> Iterator[str]:
    """The builds the pointer chains are for."""
    return (pointer["exe_sha256"] for pointer in settings["pointers"])


def create(source: SourceSettings, app: RunningApp) -> MemorySource:
    settings = parse_settings(source.settings)
    # The detector already hashed the executable if the profile lists its builds.
    chain = chain_for(settings.pointers, app.build or executable_sha256(app.process.pid))
    memory = open_process_memory(app.process.pid)
    return MemorySource(source.name, source.poll_interval, settings.encoding, chain, memory)


PLUGIN = SourcePlugin(
    type="memory",
    settings_schema=load_schema("reflektortts.sources.memory", "settings.schema.json"),
    create=create,
    builds=builds,
)
