"""The core's side of the TTS service: starts its process and sends it lines."""

import logging
import multiprocessing
from types import TracebackType

from reflektortts.tts.service import Say, Stop, run

logger = logging.getLogger(__name__)


class TtsServiceError(Exception):
    """The TTS process is not running."""


class TtsClient:
    """Runs the TTS service in its own process; usable as a context manager."""

    def __init__(self, voice: str) -> None:
        context = multiprocessing.get_context("spawn")
        self._connection, service_end = context.Pipe()
        self._process = context.Process(
            target=run,
            args=(service_end, voice, logging.getLogger().getEffectiveLevel()),
            name="reflektortts-tts",
            daemon=True,
        )
        self._process.start()
        service_end.close()

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
