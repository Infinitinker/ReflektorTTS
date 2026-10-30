"""Speech engine backed by a local Piper voice model."""

from collections.abc import Iterator
from pathlib import Path

from piper import PiperVoice

from reflektortts.tts.engine import AudioChunk, EnginePlugin
from reflektortts.tts.voices import ensure_voice


class PiperEngine:
    """Speaks with one Piper voice, loaded once from its .onnx model file."""

    def __init__(self, model_path: Path) -> None:
        self._voice = PiperVoice.load(model_path)

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        for chunk in self._voice.synthesize(text):
            yield AudioChunk(samples=chunk.audio_int16_array, sample_rate=chunk.sample_rate)


def create(voice_name: str) -> PiperEngine:
    """Speaks with a Piper voice such as "en_US-ljspeech-medium", downloading it on first use."""
    return PiperEngine(ensure_voice(voice_name))


PLUGIN = EnginePlugin(name="piper", create=create)
