from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from piper import PiperVoice, SynthesisConfig

from reflektortts.tts.engine import VoiceError
from reflektortts.tts.engines import piper as piper_engine
from reflektortts.tts.engines.piper import PiperEngine, create, list_voices


@pytest.fixture
def voices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A voices folder with one installed voice."""
    for file in ("pl_PL-test-medium.onnx", "pl_PL-test-medium.onnx.json"):
        (tmp_path / file).write_bytes(b"")
    monkeypatch.setattr(piper_engine, "voices_dir", lambda: tmp_path)
    monkeypatch.setattr(piper_engine, "downloaded_voices", lambda: ["pl_PL-test-medium"])
    return tmp_path


def test_only_installed_voices_are_listed(voices: Path) -> None:
    assert [voice.id for voice in list_voices()] == ["piper:pl_PL-test-medium"]


def test_a_voice_that_is_not_installed_is_not_downloaded(voices: Path) -> None:
    with pytest.raises(VoiceError, match="en_US-ljspeech-medium is not installed"):
        create("en_US-ljspeech-medium")
    assert sorted(path.name for path in voices.iterdir()) == ["pl_PL-test-medium.onnx", "pl_PL-test-medium.onnx.json"]


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
