"""The TTS process: speaks lines sent by the core, one at a time."""

import logging
import threading
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Protocol

from reflektortts.logs import log_to_file
from reflektortts.tts.engine import AudioChunk, TtsEngine, load_engine_plugin, parse_voice

logger = logging.getLogger(__name__)

LOG_FILE = "reflektortts-tts.log"

MAX_WAITING = 3
"""Lines that may wait their turn; past that the oldest waiting is dropped, so the voice never
falls far behind the game."""


@dataclass(frozen=True)
class Say:
    """Speak this line at rate (see TtsEngine), either cutting off the line being spoken and any
    waiting, or after them."""

    text: str
    rate: float = 1.0
    cut_off: bool = True


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


class Speaker:
    """Speaks on a background thread, one line at a time.

    A new line either cuts off the one being spoken, when a line replaced on screen is not worth
    finishing, or waits its turn (at most MAX_WAITING lines wait). on_speaking is called with True
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

    def say(self, text: str, rate: float = 1.0, cut_off: bool = True) -> None:
        with self._changed:
            if cut_off:
                self._waiting.clear()
                self._cancel.set()
            elif len(self._waiting) == MAX_WAITING:
                self._waiting.popleft()
            self._waiting.append(_Line(text, rate))
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
                cancel = self._cancel = threading.Event()
            if not speaking:
                speaking = True
                self._on_speaking(True)
            try:
                self._player.play(self._engine.synthesize(line.text, line.rate), cancel)
            except Exception:
                # A broken line or audio device must not end the service; the next line may work.
                logger.exception("Could not speak %r", line.text)


class SpeakerControl(Protocol):
    def say(self, text: str, rate: float = 1.0, cut_off: bool = True) -> None: ...

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
                speaker.say(message.text, message.rate, message.cut_off)
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


def run(connection: Connection, events: Connection, voice: str, log_level: int, log_dir: Path | None) -> None:
    """Entry point of the TTS process. Commands arrive on connection; Speaking messages go to events.

    voice is "engine:name", e.g. "windows:Microsoft Adam". Logs go to a file in log_dir when the
    core logs to files (it has no console), otherwise to the console.
    """
    if log_dir is None:
        logging.basicConfig(level=log_level, format="%(asctime)s %(processName)s %(name)s: %(message)s")
    else:
        log_to_file(log_dir / LOG_FILE)
    from reflektortts.tts.playback import Player

    parsed = parse_voice(voice)
    try:
        engine = load_engine_plugin(parsed.engine).create(parsed.name)
    except Exception as error:
        # Exiting closes the connection, so the core's next line fails with TtsServiceError.
        logger.error("Cannot use the voice %s: %s", voice, error)
        return
    logger.info("Voice %s loaded", voice)
    serve(connection, Speaker(engine, Player(), report_to(events)))
