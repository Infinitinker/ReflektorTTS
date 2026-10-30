import threading
from collections.abc import Iterable, Iterator
from multiprocessing.connection import Connection
from typing import cast

import numpy as np
import pytest

from reflektortts.tts.engine import AudioChunk
from reflektortts.tts.service import Say, Speaker, Stop, serve

TIMEOUT = 2.0


class RecordingEngine:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        self.texts.append(text)
        yield AudioChunk(samples=np.zeros(1, dtype=np.int16), sample_rate=22050)


class BlockingPlayer:
    """Plays until cancelled or until finish() is called, reporting each start."""

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
        self.calls: list[tuple[str, ...]] = []

    def say(self, text: str) -> None:
        self.calls.append(("say", text))

    def stop(self) -> None:
        self.calls.append(("stop",))

    def close(self) -> None:
        self.calls.append(("close",))


def test_serve_passes_messages_on_and_closes_when_the_core_hangs_up() -> None:
    speaker = RecordingSpeaker()
    connection = FakeConnection([Say("hello"), Stop(), "garbage"])

    serve(cast(Connection, connection), speaker)

    assert speaker.calls == [("say", "hello"), ("stop",), ("close",)]
