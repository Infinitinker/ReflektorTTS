"""Playing speech: audio written in blocks, cut off, and the silence after speech left out."""

import threading
from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from reflektortts.tts.engine import AudioChunk
from reflektortts.tts.playback import Player, without_trailing_silence


class FakeStream:
    def __init__(self, sample_rate: int, on_write: Callable[[], None] | None = None) -> None:
        self.sample_rate = sample_rate
        self.written: list[list[int]] = []
        self.stopped = False
        self.closed = False
        self.on_write = on_write

    def write(self, samples: npt.NDArray[np.int16]) -> None:
        self.written.append(samples.tolist())
        if self.on_write is not None:
            self.on_write()

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeOutputs:
    """Opens FakeStreams and remembers them."""

    def __init__(self, on_write: Callable[[], None] | None = None) -> None:
        self.streams: list[FakeStream] = []
        self.on_write = on_write

    def open(self, sample_rate: int) -> FakeStream:
        self.streams.append(FakeStream(sample_rate, self.on_write))
        return self.streams[-1]


def chunk(length: int, sample_rate: int = 20) -> AudioChunk:
    return AudioChunk(samples=np.arange(length, dtype=np.int16), sample_rate=sample_rate)


def test_play_writes_all_audio_in_blocks_and_waits_for_it() -> None:
    outputs = FakeOutputs()

    # 20 Hz makes one 50 ms block a single sample.
    assert Player(outputs.open).play([chunk(2), chunk(1)], threading.Event()) is True

    assert len(outputs.streams) == 1
    assert outputs.streams[0].written == [[0], [1], [0]]
    assert outputs.streams[0].stopped and outputs.streams[0].closed


def test_new_sample_rate_reopens_the_output() -> None:
    outputs = FakeOutputs()

    Player(outputs.open).play([chunk(1, sample_rate=20), chunk(1, sample_rate=40)], threading.Event())

    assert [stream.sample_rate for stream in outputs.streams] == [20, 40]
    assert all(stream.closed for stream in outputs.streams)


def test_cancel_cuts_off_playback_and_discards_buffered_audio() -> None:
    cancel = threading.Event()
    outputs = FakeOutputs(on_write=cancel.set)

    assert Player(outputs.open).play([chunk(5)], cancel) is False

    assert outputs.streams[0].written == [[0]]
    assert not outputs.streams[0].stopped
    assert outputs.streams[0].closed


def test_play_without_audio_opens_nothing() -> None:
    outputs = FakeOutputs()

    assert Player(outputs.open).play([], threading.Event()) is True
    assert outputs.streams == []


def test_the_silence_after_speech_is_cut_off() -> None:
    speech = np.array([0, 5, 9000, -12000, 400, 100, 0, -50, 0], dtype=np.int16)
    quiet = np.array([0, 10, -20], dtype=np.int16)

    chunks = list(without_trailing_silence([AudioChunk(speech, 22050), AudioChunk(quiet, 22050)]))

    assert [chunk.samples.tolist() for chunk in chunks] == [[0, 5, 9000, -12000, 400]]
    assert chunks[0].sample_rate == 22050
