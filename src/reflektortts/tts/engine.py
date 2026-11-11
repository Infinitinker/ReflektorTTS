"""The contract between the TTS service and speech engines, and how engines are found."""

import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol

import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)

ENGINE_GROUP = "reflektortts.tts_engines"
DEFAULT_ENGINE = "piper"
# Trained on the public-domain LJ Speech dataset, so it can be bundled and used by default.
DEFAULT_VOICE = "piper:en_US-ljspeech-medium"


@dataclass(frozen=True)
class AudioChunk:
    """A piece of synthesized speech: mono 16-bit samples."""

    samples: npt.NDArray[np.int16]
    sample_rate: int


MIN_RATE = 0.5
MAX_RATE = 2.0
"""Speaking rates users can choose: 1.0 is the voice's own pace, 2.0 twice as fast."""


class TtsEngine(Protocol):
    """Turns text into audio, yielding chunks as soon as they are ready."""

    def synthesize(self, text: str, rate: float) -> Iterator[AudioChunk]:
        """rate is a multiple of the voice's own pace, from MIN_RATE to MAX_RATE."""


class VoiceError(Exception):
    """A voice cannot be used; the message says why and what to do."""


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    """What settings and the API's voice field use: "engine:name"."""
    engine: str
    name: str
    language: str
    """BCP 47 tag, its language as a code ReflektorTTS uses (languages.language_tag), e.g. "pl-PL"."""
    engine_title: str
    """The engine's name as shown to users, e.g. "Windows"."""


def find_voice(voice: str, voices: Sequence[VoiceInfo]) -> VoiceInfo:
    """The voice with this ID; raises VoiceError, listing the others, if it is not among them."""
    for info in voices:
        if info.id == voice:
            return info
    available = ", ".join(info.id for info in voices) or "none"
    raise VoiceError(f'There is no voice "{voice}". Available: {available}.')


@dataclass(frozen=True)
class EnginePlugin:
    """What an engine registers under the reflektortts.tts_engines entry-point group.

    Importing the plugin's module must stay cheap: the core imports it to list voices,
    so heavy libraries are imported only when an engine is created.
    """

    name: str
    create: Callable[[str], TtsEngine]
    """Creates the engine speaking with the named voice; raises VoiceError if it cannot."""
    list_voices: Callable[[], list[VoiceInfo]]
    """Voices usable right now, or after a download the engine does itself."""


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


def available_voices() -> list[VoiceInfo]:
    """Voices of every engine that works on this system; an engine that fails is logged and skipped."""
    voices: list[VoiceInfo] = []
    for entry_point in entry_points(group=ENGINE_GROUP):
        try:
            voices.extend(load_engine_plugin(entry_point.name).list_voices())
        except Exception as error:
            logger.warning("Speech engine %s is not available: %s", entry_point.name, error)
    return voices
