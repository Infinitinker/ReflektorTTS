"""Speech engine backed by a local Piper voice model."""

from collections.abc import Iterator
from pathlib import Path

from reflektortts.tts.engine import DEFAULT_VOICE, AudioChunk, EnginePlugin, VoiceInfo, parse_voice
from reflektortts.tts.voices import downloaded_voices, ensure_voice


class PiperEngine:
    """Speaks with one Piper voice, loaded once from its .onnx model file."""

    def __init__(self, model_path: Path) -> None:
        # Piper pulls in onnxruntime; importing it here keeps it out of the core process.
        from piper import PiperVoice

        self._voice = PiperVoice.load(model_path)

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        for chunk in self._voice.synthesize(text):
            yield AudioChunk(samples=chunk.audio_int16_array, sample_rate=chunk.sample_rate)


def create(voice_name: str) -> PiperEngine:
    """Speaks with a Piper voice such as "en_US-ljspeech-medium", downloading it on first use."""
    return PiperEngine(ensure_voice(voice_name))


def voice_info(name: str) -> VoiceInfo:
    """Piper voice names start with the language, e.g. "en_US-ljspeech-medium"."""
    return VoiceInfo(id=f"piper:{name}", engine="piper", name=name, language=name.split("-")[0].replace("_", "-"))


def list_voices() -> list[VoiceInfo]:
    """Downloaded voices, plus the default voice, which is downloaded on first use."""
    names = set(downloaded_voices()) | {parse_voice(DEFAULT_VOICE).name}
    return [voice_info(name) for name in sorted(names)]


PLUGIN = EnginePlugin(name="piper", create=create, list_voices=list_voices)
