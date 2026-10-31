"""Speech engine using the voices built into Windows (Windows.Media.SpeechSynthesis)."""

import asyncio
import io
import wave
from collections.abc import Iterable, Iterator

import numpy as np
from winrt.windows.media.speechsynthesis import SpeechSynthesizer, VoiceInformation
from winrt.windows.storage.streams import DataReader

from reflektortts.tts.engine import AudioChunk, EnginePlugin, VoiceError, VoiceInfo


def find_voice(name: str, voices: Iterable[VoiceInformation]) -> VoiceInformation:
    """Finds a voice by its display name; the "Microsoft " prefix may be left out."""
    wanted = {name.lower(), f"microsoft {name}".lower()}
    available = list(voices)
    for voice in available:
        if voice.display_name.lower() in wanted:
            return voice
    names = ", ".join(voice.display_name for voice in available) or "none"
    raise VoiceError(
        f'Windows has no voice called "{name}" (installed: {names}). '
        "Voices are added in Windows Settings > Time & language > Speech."
    )


def wav_to_chunk(wav_bytes: bytes) -> AudioChunk:
    """Converts a 16-bit PCM WAV file into a mono AudioChunk."""
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        if wav.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit audio from Windows, got {wav.getsampwidth() * 8}-bit")
        channels = wav.getnchannels()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        rate = wav.getframerate()
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return AudioChunk(samples=samples.astype(np.int16), sample_rate=rate)


async def _synthesize_wav(voice: VoiceInformation, text: str, rate: float) -> bytes:
    synthesizer = SpeechSynthesizer()
    synthesizer.voice = voice
    synthesizer.options.speaking_rate = rate
    stream = await synthesizer.synthesize_text_to_stream_async(text)
    reader = DataReader(stream.get_input_stream_at(0))
    await reader.load_async(stream.size)
    data = bytearray(stream.size)
    reader.read_bytes(data)
    return bytes(data)


class WindowsEngine:
    """Speaks with a voice installed in Windows. Windows synthesizes a whole line at once."""

    def __init__(self, voice_name: str) -> None:
        self._voice = find_voice(voice_name, SpeechSynthesizer.all_voices)

    def synthesize(self, text: str, rate: float) -> Iterator[AudioChunk]:
        yield wav_to_chunk(asyncio.run(_synthesize_wav(self._voice, text, rate)))


def list_voices() -> list[VoiceInfo]:
    return [
        VoiceInfo(
            id=f"windows:{voice.display_name}", engine="windows", name=voice.display_name, language=voice.language
        )
        for voice in SpeechSynthesizer.all_voices
    ]


PLUGIN = EnginePlugin(name="windows", create=WindowsEngine, list_voices=list_voices)
