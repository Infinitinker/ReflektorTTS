"""The contract between the TTS service and speech engines."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class AudioChunk:
    """A piece of synthesized speech: mono 16-bit samples."""

    samples: npt.NDArray[np.int16]
    sample_rate: int


class TtsEngine(Protocol):
    """Turns text into audio, yielding chunks as soon as they are ready."""

    def synthesize(self, text: str) -> Iterator[AudioChunk]: ...
