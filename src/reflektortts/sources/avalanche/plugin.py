"""Registers the avalanche source: its settings schema and how to create it for a running game."""

from reflektortts.games.detector import RunningGame
from reflektortts.pipeline.plugins import SourcePlugin, load_schema
from reflektortts.process_memory.executable import executable_sha256
from reflektortts.process_memory.memory import open_process_memory
from reflektortts.process_memory.pointer import chain_for, parse_pointer_chains
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.avalanche.source import AvalancheSource


def create(source: SourceSettings, game: RunningGame) -> AvalancheSource:
    chains = parse_pointer_chains(source.settings["pointers"])
    chain = chain_for(chains, executable_sha256(game.process.pid))
    memory = open_process_memory(game.process.pid)
    return AvalancheSource(source.name, source.poll_interval, chain, memory)


PLUGIN = SourcePlugin(
    type="avalanche",
    settings_schema=load_schema("reflektortts.sources.avalanche", "settings.schema.json"),
    create=create,
)
