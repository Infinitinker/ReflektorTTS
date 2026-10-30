"""Registers the memory source: its settings schema and how to create it for a running game."""

import hashlib
import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

import psutil

from reflektortts.games.detector import RunningGame
from reflektortts.pipeline.plugins import SourcePlugin
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.memory.pointer import parse_address
from reflektortts.sources.memory.process_memory import ProcessMemoryError, open_process_memory
from reflektortts.sources.memory.source import MemorySettings, MemorySource, PointerChain


def parse_settings(settings: Mapping[str, Any]) -> MemorySettings:
    """Turns schema-validated profile fields into MemorySettings."""
    return MemorySettings(
        encoding=settings["encoding"],
        pointers=tuple(
            PointerChain(
                exe_sha256=pointer["exe_sha256"],
                base=parse_address(pointer["address"]),
                offsets=tuple(int(offset, 16) for offset in pointer["offsets"]),
            )
            for pointer in settings["pointers"]
        ),
    )


def executable_sha256(pid: int) -> str:
    try:
        path = psutil.Process(pid).exe()
        with open(path, "rb") as executable:
            return hashlib.file_digest(executable, "sha256").hexdigest()
    except (psutil.Error, OSError) as error:
        raise ProcessMemoryError(f"Cannot identify the game's version: {error}") from error


def create(source: SourceSettings, game: RunningGame) -> MemorySource:
    settings = parse_settings(source.settings)
    exe_sha256 = executable_sha256(game.process.pid)
    memory = open_process_memory(game.process.pid)
    return MemorySource(source.name, source.poll_interval, settings, memory, exe_sha256)


PLUGIN = SourcePlugin(
    type="memory",
    settings_schema=json.loads(
        resources.files("reflektortts.sources.memory").joinpath("settings.schema.json").read_text("utf-8")
    ),
    create=create,
)
