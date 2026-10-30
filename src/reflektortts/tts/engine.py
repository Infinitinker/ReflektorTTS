"""The contract between the TTS service and speech engines, and how engines are found."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol

import numpy as np
import numpy.typing as npt

ENGINE_GROUP = "reflektortts.tts_engines"
DEFAULT_ENGINE = "piper"
# Trained on the public-domain LJ Speech dataset, so it can be bundled and used by default.
DEFAULT_VOICE = "piper:en_US-ljspeech-medium"


@dataclass(frozen=True)
class AudioChunk:
    """A piece of synthesized speech: mono 16-bit samples."""

    samples: npt.NDArray[np.int16]
    sample_rate: int


class TtsEngine(Protocol):
    """Turns text into audio, yielding chunks as soon as they are ready."""

    def synthesize(self, text: str) -> Iterator[AudioChunk]: ...


class VoiceError(Exception):
    """A voice cannot be used; the message says why and what to do."""


@dataclass(frozen=True)
class EnginePlugin:
    """What an engine registers under the reflektortts.tts_engines entry-point group."""

    name: str
    create: Callable[[str], TtsEngine]
    """Creates the engine speaking with the named voice; raises VoiceError if it cannot."""


@dataclass(frozen=True)
class Voice:
    engine: str
    name: str


def parse_voice(text: str) -> Voice:
    """Parses "engine:name", e.g. "windows:Microsoft Adam"; a bare name is a Piper voice."""
    engine, separator, name = text.partition(":")
    if not separator:
        return Voice(DEFAULT_ENGINE, text)
    return Voice(engine.strip().lower(), name.strip())


def load_engine_plugin(name: str) -> EnginePlugin:
    """Imports only the named engine, so unused engines' heavy libraries are never loaded."""
    for entry_point in entry_points(group=ENGINE_GROUP, name=name):
        plugin = entry_point.load()
        if not isinstance(plugin, EnginePlugin):
            raise TypeError(f"Entry point {entry_point.value} in {ENGINE_GROUP} is not an EnginePlugin")
        return plugin
    installed = ", ".join(sorted(entry_point.name for entry_point in entry_points(group=ENGINE_GROUP)))
    raise VoiceError(f'There is no speech engine called "{name}" (installed: {installed}).')
