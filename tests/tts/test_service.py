"""The TTS process: lines spoken in order, cut off, caught up when they waited, and messages from the core."""

import threading
from collections.abc import Iterable, Iterator
from multiprocessing.connection import Connection
from typing import cast

import numpy as np
import pytest

from reflektortts.tts.engine import AudioChunk
from reflektortts.tts.service import NewLine, Say, Speaker, Stop, serve

TIMEOUT = 2.0


class RecordingEngine:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.rates: list[float] = []

    def synthesize(self, text: str, rate: float) -> Iterator[AudioChunk]:
        self.texts.append(text)
        self.rates.append(rate)
        yield AudioChunk(samples=np.zeros(1, dtype=np.int16), sample_rate=22050)


class BlockingPlayer:
    """Plays until canceled or until finish() is called, reporting each start."""

    def __init__(self) -> None:
        self.started = threading.Semaphore(0)
        self.outcomes: list[bool] = []
        self.done = threading.Semaphore(0)
        self._finish = threading.Event()

    def play(self, chunks: Iterable[AudioChunk], cancel: threading.Event) -> bool:
        list(chunks)
        self._finish.clear()
        self.started.release()
        while not cancel.is_set() and not self._finish.is_set():
            cancel.wait(0.01)
        self.outcomes.append(not cancel.is_set())
        self.done.release()
        return not cancel.is_set()

    def finish(self) -> None:
        self._finish.set()


class FailingPlayer:
    def __init__(self) -> None:
        self.calls = 0
        self.called = threading.Semaphore(0)

    def play(self, chunks: Iterable[AudioChunk], cancel: threading.Event) -> bool:
        self.calls += 1
        self.called.release()
        raise OSError("audio device unplugged")


def test_new_line_cuts_off_the_current_one() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("first")
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("second")
        assert player.started.acquire(timeout=TIMEOUT)
        player.finish()
        assert player.done.acquire(timeout=TIMEOUT) and player.done.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert engine.texts == ["first", "second"]
    assert player.outcomes == [False, True]


def test_stop_cuts_off_the_current_line() -> None:
    player = BlockingPlayer()
    speaker = Speaker(RecordingEngine(), player)
    try:
        speaker.say("line")
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.stop()
        assert player.done.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert player.outcomes == [False]


def finish_lines(player: BlockingPlayer, count: int) -> None:
    """Lets count lines finish one after another, the first of them already playing."""
    for i in range(count):
        player.finish()
        assert player.done.acquire(timeout=TIMEOUT)
        if i < count - 1:
            assert player.started.acquire(timeout=TIMEOUT)


def test_waiting_lines_are_spoken_in_order_at_their_rate() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("first", 1.0, new_line=NewLine.WAIT)
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("second", 1.5, new_line=NewLine.WAIT)
        speaker.say("third", 2.0, new_line=NewLine.WAIT)
        finish_lines(player, 3)
    finally:
        speaker.close()

    assert engine.texts == ["first", "second", "third"]
    assert engine.rates == [1.0, 1.5, 2.0]
    assert player.outcomes == [True, True, True]


def test_lines_that_waited_catch_up_faster_the_more_wait_after_them() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("speaking", 1.0, new_line=NewLine.SPEED_UP)
        assert player.started.acquire(timeout=TIMEOUT)
        for text in ("a", "b", "c"):
            speaker.say(text, 1.0, new_line=NewLine.SPEED_UP)
        finish_lines(player, 4)
    finally:
        speaker.close()

    assert engine.texts == ["speaking", "a", "b", "c"]
    assert engine.rates == [1.0, 1.75, 1.5, 1.25]


def test_catching_up_stops_at_the_fastest_reading_speed() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("speaking", 1.5, new_line=NewLine.SPEED_UP)
        assert player.started.acquire(timeout=TIMEOUT)
        for text in ("a", "b", "c"):
            speaker.say(text, 1.5, new_line=NewLine.SPEED_UP)
        finish_lines(player, 4)
    finally:
        speaker.close()

    assert engine.rates == [1.5, 2.0, 2.0, 1.875]


def test_one_line_that_waited_is_spoken_faster_and_one_in_silence_is_not() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("speaking", 1.0, new_line=NewLine.SPEED_UP)
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("waited", 1.0, new_line=NewLine.SPEED_UP)
        finish_lines(player, 2)
        speaker.say("in silence", 1.0, new_line=NewLine.SPEED_UP)
        assert player.started.acquire(timeout=TIMEOUT)
        finish_lines(player, 1)
    finally:
        speaker.close()

    assert engine.rates == [1.0, 1.25, 1.0]


def test_past_the_limit_the_oldest_waiting_line_is_dropped() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("speaking", new_line=NewLine.WAIT)
        assert player.started.acquire(timeout=TIMEOUT)
        for text in ("a", "b", "c", "d"):
            speaker.say(text, new_line=NewLine.WAIT)
        finish_lines(player, 4)
    finally:
        speaker.close()

    assert engine.texts == ["speaking", "b", "c", "d"]


def test_stopping_a_line_moves_on_to_the_next_waiting_one() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("long", new_line=NewLine.WAIT)
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("next", new_line=NewLine.WAIT)
        speaker.stop(drop_waiting=False)
        assert player.done.acquire(timeout=TIMEOUT)
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.stop()
        assert player.done.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert engine.texts == ["long", "next"]
    assert player.outcomes == [False, False]


def test_a_cutting_line_drops_the_waiting_ones() -> None:
    engine, player = RecordingEngine(), BlockingPlayer()
    speaker = Speaker(engine, player)
    try:
        speaker.say("first", new_line=NewLine.WAIT)
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("waiting", new_line=NewLine.WAIT)
        speaker.say("urgent", new_line=NewLine.CUT_OFF)
        assert player.started.acquire(timeout=TIMEOUT)
        player.finish()
        assert player.done.acquire(timeout=TIMEOUT) and player.done.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert engine.texts == ["first", "urgent"]


class SpeakingRecorder:
    def __init__(self) -> None:
        self.states: list[bool] = []
        self.changed = threading.Semaphore(0)

    def __call__(self, active: bool) -> None:
        self.states.append(active)
        self.changed.release()


def test_speaking_is_reported_once_per_stretch_of_speech() -> None:
    player, recorder = BlockingPlayer(), SpeakingRecorder()
    speaker = Speaker(RecordingEngine(), player, recorder)
    try:
        speaker.say("first")
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.say("second")
        assert player.started.acquire(timeout=TIMEOUT)
        player.finish()
        assert recorder.changed.acquire(timeout=TIMEOUT) and recorder.changed.acquire(timeout=TIMEOUT)
        speaker.say("third")
        assert player.started.acquire(timeout=TIMEOUT)
        speaker.stop()
        assert recorder.changed.acquire(timeout=TIMEOUT) and recorder.changed.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert recorder.states == [True, False, True, False]


def test_a_failing_line_does_not_stop_the_speaker(caplog: pytest.LogCaptureFixture) -> None:
    player = FailingPlayer()
    speaker = Speaker(RecordingEngine(), player)
    try:
        speaker.say("one")
        assert player.called.acquire(timeout=TIMEOUT)
        speaker.say("two")
        assert player.called.acquire(timeout=TIMEOUT)
    finally:
        speaker.close()

    assert player.calls == 2
    assert "Could not speak 'one'" in caplog.text


class FakeConnection:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages

    def recv(self) -> object:
        if not self._messages:
            raise EOFError
        return self._messages.pop(0)


class RecordingSpeaker:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def say(self, text: str, rate: float = 1.0, new_line: NewLine = NewLine.CUT_OFF) -> None:
        self.calls.append(("say", text, rate, new_line))

    def stop(self, drop_waiting: bool = True) -> None:
        self.calls.append(("stop", drop_waiting))

    def close(self) -> None:
        self.calls.append(("close",))


def test_serve_passes_messages_on_and_closes_when_the_core_hangs_up() -> None:
    speaker = RecordingSpeaker()
    connection = FakeConnection([Say("hello", 1.5, NewLine.WAIT), Stop(drop_waiting=False), "garbage"])

    serve(cast(Connection, connection), speaker)

    assert speaker.calls == [("say", "hello", 1.5, NewLine.WAIT), ("stop", False), ("close",)]
