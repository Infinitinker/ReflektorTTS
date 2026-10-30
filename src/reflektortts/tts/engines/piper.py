"""Speech engine backed by a local Piper voice model."""

from collections.abc import Iterator
from pathlib import Path

from piper import PiperVoice

from reflektortts.tts.engine import AudioChunk


class PiperEngine:
    """Speaks with one Piper voice, loaded once from its .onnx model file."""

    def __init__(self, model_path: Path) -> None:
        self._voice = PiperVoice.load(model_path)

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        for chunk in self._voice.synthesize(text):
            yield AudioChunk(samples=chunk.audio_int16_array, sample_rate=chunk.sample_rate)
