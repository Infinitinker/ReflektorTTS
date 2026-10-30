"""The TTS process: speaks lines sent by the core, one at a time, newest first."""

import logging
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Protocol

from reflektortts.tts.engine import AudioChunk, TtsEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Say:
    """Speak this line, cutting off the one being spoken."""

    text: str


@dataclass(frozen=True)
class Stop:
    """Stop speaking and drop any line waiting to be spoken."""


class AudioPlayer(Protocol):
    def play(self, chunks: Iterable[AudioChunk], cancel: threading.Event) -> bool: ...


class Speaker:
    """Speaks on a background thread; a new line cuts off the current one.

    Only the newest line matters: in a game, a line that has been replaced on screen
    is not worth finishing.
    """

    def __init__(self, engine: TtsEngine, player: AudioPlayer) -> None:
        self._engine = engine
        self._player = player
        self._changed = threading.Condition()
        self._pending: str | None = None
        self._cancel = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        with self._changed:
            self._pending = text
            self._cancel.set()
            self._changed.notify()

    def stop(self) -> None:
        with self._changed:
            self._pending = None
            self._cancel.set()

    def close(self) -> None:
        with self._changed:
            self._closed = True
            self._cancel.set()
            self._changed.notify()
        self._thread.join()

    def _run(self) -> None:
        while True:
            with self._changed:
                while self._pending is None:
                    if self._closed:
                        return
                    self._changed.wait()
                if self._closed:
                    return
                text, self._pending = self._pending, None
                cancel = self._cancel = threading.Event()
            try:
                self._player.play(self._engine.synthesize(text), cancel)
            except Exception:
                # A broken line or audio device must not end the service; the next line may work.
                logger.exception("Could not speak %r", text)


class SpeakerControl(Protocol):
    def say(self, text: str) -> None: ...

    def stop(self) -> None: ...

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
                speaker.say(message.text)
            elif isinstance(message, Stop):
                speaker.stop()
            else:
                logger.error("Ignoring unknown TTS message %r", message)
    finally:
        speaker.close()


def run(connection: Connection, voice: str, log_level: int) -> None:
    """Entry point of the TTS process."""
    logging.basicConfig(level=log_level, format="%(asctime)s %(processName)s %(name)s: %(message)s")
    # Piper pulls in onnxruntime; importing it only here keeps it out of the core process.
    from reflektortts.tts.engines.piper import PiperEngine
    from reflektortts.tts.playback import Player
    from reflektortts.tts.voices import ensure_voice

    engine = PiperEngine(ensure_voice(voice))
    logger.info("Voice %s loaded", voice)
    serve(connection, Speaker(engine, Player()))
