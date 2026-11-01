"""Plays synthesized speech on the default audio output, and lets it be cut off."""

import threading
from collections.abc import Callable, Iterable
from typing import Protocol

import numpy as np
import numpy.typing as npt

from reflektortts.tts.engine import AudioChunk

# Audio is written in short blocks so a cancel takes effect within one block.
BLOCK_SECONDS = 0.05


class OutputStream(Protocol):
    """The part of an audio output stream the player uses."""

    def write(self, samples: npt.NDArray[np.int16]) -> object: ...

    def stop(self) -> None:
        """Waits until written audio has played."""

    def close(self) -> None:
        """Discards audio that has not played yet and releases the device."""


def open_default_output(sample_rate: int) -> OutputStream:
    import sounddevice

    stream = sounddevice.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
    stream.start()
    output: OutputStream = stream
    return output


class Player:
    """Plays audio chunks on an output opened per sample rate."""

    def __init__(self, open_output: Callable[[int], OutputStream] = open_default_output) -> None:
        self._open_output = open_output

    def play(self, chunks: Iterable[AudioChunk], cancel: threading.Event) -> bool:
        """Plays chunks until they run out or cancel is set; returns False if canceled."""
        stream: OutputStream | None = None
        stream_rate = 0
        try:
            for chunk in chunks:
                if stream is None or chunk.sample_rate != stream_rate:
                    if stream is not None:
                        stream.stop()
                        stream.close()
                    stream = self._open_output(chunk.sample_rate)
                    stream_rate = chunk.sample_rate
                block = max(1, int(chunk.sample_rate * BLOCK_SECONDS))
                for start in range(0, len(chunk.samples), block):
                    if cancel.is_set():
                        return False
                    stream.write(chunk.samples[start : start + block])
            if stream is not None and not cancel.is_set():
                stream.stop()
            return not cancel.is_set()
        finally:
            if stream is not None:
                stream.close()
