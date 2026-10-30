"""The core's side of the TTS service: starts its process, sends it lines and hears when it speaks."""

import logging
import multiprocessing
import threading
from collections.abc import Callable
from multiprocessing.connection import Connection
from types import TracebackType

from reflektortts.tts.service import Say, Speaking, Stop, run

logger = logging.getLogger(__name__)


class TtsServiceError(Exception):
    """The TTS process is not running."""


def receive_events(events: Connection, on_speaking: Callable[[bool], None]) -> None:
    """Passes the service's Speaking messages on until it exits; one that ends mid-line counts as falling silent."""
    speaking = False
    try:
        while True:
            try:
                message = events.recv()
            except (EOFError, OSError):
                break
            if isinstance(message, Speaking):
                speaking = message.active
                on_speaking(speaking)
            else:
                logger.error("Ignoring unknown TTS event %r", message)
    finally:
        events.close()
        if speaking:
            on_speaking(False)


class TtsClient:
    """Runs the TTS service in its own process; usable as a context manager.

    on_speaking is called, on a thread of its own, when the service starts speaking and when it falls silent.
    """

    def __init__(self, voice: str, on_speaking: Callable[[bool], None] = lambda active: None) -> None:
        context = multiprocessing.get_context("spawn")
        self._connection, service_end = context.Pipe()
        events, service_events = context.Pipe(duplex=False)
        self._process = context.Process(
            target=run,
            args=(service_end, service_events, voice, logging.getLogger().getEffectiveLevel()),
            name="reflektortts-tts",
            daemon=True,
        )
        self._process.start()
        service_end.close()
        service_events.close()
        self._events = threading.Thread(
            target=receive_events, args=(events, on_speaking), name="tts-events", daemon=True
        )
        self._events.start()

    def say(self, text: str) -> None:
        """Speaks text, cutting off the line being spoken."""
        self._send(Say(text))

    def stop(self) -> None:
        self._send(Stop())

    def close(self, timeout: float = 5.0) -> None:
        self._connection.close()
        self._process.join(timeout)
        if self._process.is_alive():
            logger.warning("TTS process did not exit within %.0f s; terminating it", timeout)
            self._process.terminate()
            self._process.join()
        self._events.join(timeout)

    def __enter__(self) -> "TtsClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _send(self, message: Say | Stop) -> None:
        try:
            self._connection.send(message)
        except OSError as error:
            raise TtsServiceError(
                f"The speech service stopped (exit code {self._process.exitcode}); see the log for why."
            ) from error
