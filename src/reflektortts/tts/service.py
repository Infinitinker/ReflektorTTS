"""The TTS process: speaks lines sent by the core, one at a time."""

import logging
import threading
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from multiprocessing.connection import Connection
from typing import Protocol

from reflektortts.tts.engine import MAX_RATE, AudioChunk, TtsEngine, load_engine_plugin, parse_voice
from reflektortts.tts.playback import without_trailing_silence

logger = logging.getLogger(__name__)

MAX_WAITING = 3
"""Lines that may wait their turn; past that the oldest waiting is dropped, so the voice never
falls far behind the app."""
SPEED_UP_STEP = 0.25
"""How much faster a line is spoken, with NewLine.SPEED_UP, if it waited, and for each line
waiting after it."""


class NewLine(StrEnum):
    """What a new line does while another is spoken."""

    WAIT = "wait"
    """Waits its turn."""
    CUT_OFF = "cut_off"
    """Cuts off the line being spoken and drops those waiting, when a line replaced on screen is
    not worth finishing."""
    SPEED_UP = "speed_up"
    """Waits its turn, and a line that waited is spoken faster, the more so the more wait after
    it, up to MAX_RATE."""


@dataclass(frozen=True)
class Say:
    """Speak this line at rate (see TtsEngine), doing with the lines spoken and waiting as
    new_line says."""

    text: str
    rate: float = 1.0
    new_line: NewLine = NewLine.CUT_OFF


@dataclass(frozen=True)
class Stop:
    """Stop the line being spoken; drop_waiting also drops the lines waiting their turn."""

    drop_waiting: bool = True


@dataclass(frozen=True)
class Speaking:
    """Sent to the core when the service starts speaking (active) and when it falls silent."""

    active: bool


class AudioPlayer(Protocol):
    def play(self, chunks: Iterable[AudioChunk], cancel: threading.Event) -> bool: ...


@dataclass(frozen=True)
class _Line:
    text: str
    rate: float
    speed_up: bool = False


class Speaker:
    """Speaks on a background thread, one line at a time.

    A new line cuts off the one being spoken or waits its turn, as NewLine says; at most
    MAX_WAITING lines wait, the oldest dropped first. on_speaking is called with True
    when a line starts after silence and with False once nothing is playing or waiting; a line
    cutting off or following another does not count as silence.
    """

    def __init__(
        self,
        engine: TtsEngine,
        player: AudioPlayer,
        on_speaking: Callable[[bool], None] = lambda active: None,
    ) -> None:
        self._engine = engine
        self._player = player
        self._on_speaking = on_speaking
        self._changed = threading.Condition()
        self._waiting: deque[_Line] = deque()
        self._cancel = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._thread.start()

    def say(self, text: str, rate: float = 1.0, new_line: NewLine = NewLine.CUT_OFF) -> None:
        with self._changed:
            if new_line is NewLine.CUT_OFF:
                self._waiting.clear()
                self._cancel.set()
            elif len(self._waiting) == MAX_WAITING:
                self._waiting.popleft()
            self._waiting.append(_Line(text, rate, speed_up=new_line is NewLine.SPEED_UP))
            self._changed.notify()

    def stop(self, drop_waiting: bool = True) -> None:
        with self._changed:
            if drop_waiting:
                self._waiting.clear()
            self._cancel.set()

    def close(self) -> None:
        with self._changed:
            self._closed = True
            self._cancel.set()
            self._changed.notify()
        self._thread.join()

    def _run(self) -> None:
        speaking = False
        while True:
            with self._changed:
                idle = not self._waiting
            if idle and speaking:
                speaking = False
                self._on_speaking(False)
            with self._changed:
                while not self._waiting:
                    if self._closed:
                        return
                    self._changed.wait()
                if self._closed:
                    return
                line = self._waiting.popleft()
                # Still speaking means the previous line just ended, so this one waited its turn.
                late = len(self._waiting) + (1 if speaking else 0)
                rate = _catching_up(line.rate, late) if line.speed_up else line.rate
                cancel = self._cancel = threading.Event()
            if not speaking:
                speaking = True
                self._on_speaking(True)
            try:
                self._player.play(without_trailing_silence(self._engine.synthesize(line.text, rate)), cancel)
            except Exception:
                # A broken line or audio device must not end the service; the next line may work.
                logger.exception("Could not speak %r", line.text)


def _catching_up(rate: float, late: int) -> float:
    """The rate for a line that is late by that many lines (itself, if it waited, and those waiting
    after it): SPEED_UP_STEP faster for each, at most MAX_RATE."""
    return max(rate, min(MAX_RATE, rate * (1 + SPEED_UP_STEP * late)))


class SpeakerControl(Protocol):
    def say(self, text: str, rate: float = 1.0, new_line: NewLine = NewLine.CUT_OFF) -> None: ...

    def stop(self, drop_waiting: bool = True) -> None: ...

    def close(self) -> None: ...


def serve(connection: Connection, speaker: SpeakerControl) -> None:
    """Passes messages from the core to the speaker until the core closes the connection."""
    try:
        while True:
            try:
                message = connection.recv()
            except EOFError:
                return
            if isinstance(message, Say):
                speaker.say(message.text, message.rate, message.new_line)
            elif isinstance(message, Stop):
                speaker.stop(message.drop_waiting)
            else:
                logger.error("Ignoring unknown TTS message %r", message)
    finally:
        speaker.close()


def report_to(events: Connection) -> Callable[[bool], None]:
    """Sends Speaking messages to the core; a core that has gone away is not an error here."""

    def report(active: bool) -> None:
        try:
            events.send(Speaking(active))
        except OSError:
            logger.debug("The core stopped listening for speaking events")

    return report


def run(connection: Connection, events: Connection, voice: str) -> None:
    """The TTS service, run by reflektortts.tts.process. Commands arrive on connection; Speaking
    messages go to events. voice is "engine:name", e.g. "windows:Microsoft Adam"."""
    try:
        from reflektortts.tts.playback import Player

        parsed = parse_voice(voice)
        engine = load_engine_plugin(parsed.engine).create(parsed.name)
        player = Player()
    except Exception as error:
        # Exiting closes the connection, so the core's next line fails with TtsServiceError.
        logger.error("Cannot use the voice %s: %s", voice, error)
        return
    logger.info("Voice %s loaded", voice)
    serve(connection, Speaker(engine, player, report_to(events)))
