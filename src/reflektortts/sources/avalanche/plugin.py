"""Registers the avalanche source: its settings schema and how to create it for a running game."""

from collections.abc import Iterator, Mapping
from typing import Any

from reflektortts.apps.detector import RunningApp
from reflektortts.apps.executable import executable_path, executable_sha256
from reflektortts.pipeline.plugins import SourcePlugin, load_schema
from reflektortts.process_memory.memory import open_process_memory
from reflektortts.process_memory.pointer import chain_for, parse_pointer_chains
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.avalanche.line_texts import LineTexts
from reflektortts.sources.avalanche.source import AvalancheSource


def builds(settings: Mapping[str, Any]) -> Iterator[str]:
    """The builds the pointer chains are for."""
    return (pointer["exe_sha256"] for pointer in settings["pointers"])


def create(source: SourceSettings, game: RunningApp) -> AvalancheSource:
    chains = parse_pointer_chains(source.settings["pointers"])
    # The detector already hashed the executable if the profile lists its builds.
    chain = chain_for(chains, game.build or executable_sha256(game.process.pid))
    texts = LineTexts(executable_path(game.process.pid).parent)
    memory = open_process_memory(game.process.pid)
    return AvalancheSource(source.name, source.poll_interval, chain, memory, texts)


PLUGIN = SourcePlugin(
    type="avalanche",
    settings_schema=load_schema("reflektortts.sources.avalanche", "settings.schema.json"),
    create=create,
    builds=builds,
)
