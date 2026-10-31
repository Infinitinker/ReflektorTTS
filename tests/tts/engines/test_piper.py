from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from piper import PiperVoice, SynthesisConfig

from reflektortts.tts.engines.piper import PiperEngine


class FakeVoice:
    config = SimpleNamespace(length_scale=1.2)

    def __init__(self) -> None:
        self.length_scales: list[float | None] = []

    def synthesize(self, text: str, syn_config: SynthesisConfig) -> list[SimpleNamespace]:
        self.length_scales.append(syn_config.length_scale)
        return [
            SimpleNamespace(audio_int16_array=np.array([1, 2], dtype=np.int16), sample_rate=22050),
            SimpleNamespace(audio_int16_array=np.array([3], dtype=np.int16), sample_rate=22050),
        ]


def test_synthesize_yields_one_chunk_per_piper_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[Path] = []

    def fake_load(path: Path) -> FakeVoice:
        loaded.append(path)
        return FakeVoice()

    monkeypatch.setattr(PiperVoice, "load", fake_load)

    chunks = list(PiperEngine(Path("voice.onnx")).synthesize("Hello", 1.0))

    assert loaded == [Path("voice.onnx")]
    assert [chunk.samples.tolist() for chunk in chunks] == [[1, 2], [3]]
    assert all(chunk.sample_rate == 22050 for chunk in chunks)


def test_rate_shortens_the_voice_s_own_sound_length(monkeypatch: pytest.MonkeyPatch) -> None:
    voice = FakeVoice()
    monkeypatch.setattr(PiperVoice, "load", lambda path: voice)

    list(PiperEngine(Path("voice.onnx")).synthesize("Hello", 2.0))

    assert voice.length_scales == [pytest.approx(0.6)]
