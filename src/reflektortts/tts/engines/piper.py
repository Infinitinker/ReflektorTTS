"""Speech engine backed by a local Piper voice model."""

from collections.abc import Iterator
from pathlib import Path

from reflektortts.languages import language_tag
from reflektortts.tts.engine import AudioChunk, EnginePlugin, VoiceError, VoiceInfo
from reflektortts.tts.voices import downloaded_voices, voices_dir

SPOKEN_PHONEME_TYPES = frozenset({"espeak", "text", "hebrew"})
"""How the voices ReflektorTTS can run turn text into sounds (their config's phoneme_type). Piper's
readers for Chinese pinyin, Japanese and Thai voices need packages ReflektorTTS does not install,
and newer types (Lithuanian) a newer Piper."""


class PiperEngine:
    """Speaks with one Piper voice, loaded once from its .onnx model file."""

    def __init__(self, model_path: Path) -> None:
        # Piper pulls in onnxruntime; importing it here keeps it out of the core process.
        import onnxruntime
        from piper import PiperVoice

        # Its official builds send usage events to Windows' diagnostic data unless told not to.
        onnxruntime.disable_telemetry_events()
        self._voice = PiperVoice.load(model_path)

    def synthesize(self, text: str, rate: float) -> Iterator[AudioChunk]:
        from piper import SynthesisConfig

        # Piper sets pace as the length of sounds, relative to the voice's own.
        config = SynthesisConfig(length_scale=self._voice.config.length_scale / rate)
        for chunk in self._voice.synthesize(text, syn_config=config):
            yield AudioChunk(samples=chunk.audio_int16_array, sample_rate=chunk.sample_rate)


def create(voice_name: str) -> PiperEngine:
    """Speaks with an installed Piper voice such as "en_US-ljspeech-medium"; never downloads one."""
    if voice_name not in downloaded_voices():
        raise VoiceError(f"The voice {voice_name} is not installed.")
    return PiperEngine(voices_dir() / f"{voice_name}.onnx")


def voice_info(name: str) -> VoiceInfo:
    """Piper voice names start with the language, e.g. "en_US-ljspeech-medium"."""
    language = language_tag(name.split("-")[0])
    return VoiceInfo(id=f"piper:{name}", engine="piper", name=name, language=language, engine_title="Piper")


def list_voices() -> list[VoiceInfo]:
    """The installed (downloaded) voices."""
    return [voice_info(name) for name in downloaded_voices()]


PLUGIN = EnginePlugin(name="piper", create=create, list_voices=list_voices)
