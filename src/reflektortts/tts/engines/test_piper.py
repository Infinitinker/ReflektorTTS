from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from piper import PiperVoice

from reflektortts.tts.engines.piper import PiperEngine


class FakeVoice:
    def synthesize(self, text: str) -> list[SimpleNamespace]:
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

    chunks = list(PiperEngine(Path("voice.onnx")).synthesize("Hello"))

    assert loaded == [Path("voice.onnx")]
    assert [chunk.samples.tolist() for chunk in chunks] == [[1, 2], [3]]
    assert all(chunk.sample_rate == 22050 for chunk in chunks)
