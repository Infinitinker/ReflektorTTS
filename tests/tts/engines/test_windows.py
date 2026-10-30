import io
import wave
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

pytest.importorskip("winrt.windows.media.speechsynthesis", reason="Windows voices exist only on Windows")

from reflektortts.tts.engine import VoiceError  # noqa: E402
from reflektortts.tts.engines.windows import find_voice, wav_to_chunk  # noqa: E402


def wav(samples: list[int], channels: int = 1, rate: int = 16000, width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(width)
        file.setframerate(rate)
        file.writeframes(np.array(samples, dtype="<i2").tobytes() if width == 2 else bytes(samples))
    return buffer.getvalue()


def voices(*names: str) -> Any:
    return cast(Any, [SimpleNamespace(display_name=name) for name in names])


def test_mono_wav_becomes_a_chunk() -> None:
    chunk = wav_to_chunk(wav([1, -2, 3], rate=22050))

    assert chunk.samples.tolist() == [1, -2, 3]
    assert chunk.samples.dtype == np.int16
    assert chunk.sample_rate == 22050


def test_stereo_wav_is_mixed_to_mono() -> None:
    chunk = wav_to_chunk(wav([100, 300, -10, -30], channels=2))

    assert chunk.samples.tolist() == [200, -20]


def test_8_bit_wav_is_rejected() -> None:
    with pytest.raises(ValueError, match="16-bit"):
        wav_to_chunk(wav([1, 2], width=1))


def test_voice_is_found_with_or_without_the_microsoft_prefix() -> None:
    installed = voices("Microsoft Paulina", "Microsoft Adam")

    assert find_voice("Microsoft Adam", installed).display_name == "Microsoft Adam"
    assert find_voice("adam", installed).display_name == "Microsoft Adam"


def test_missing_voice_lists_the_installed_ones_and_where_to_add_more() -> None:
    with pytest.raises(VoiceError, match=r'no voice called "Zira" \(installed: Microsoft Adam\)\. .*Settings'):
        find_voice("Zira", voices("Microsoft Adam"))
