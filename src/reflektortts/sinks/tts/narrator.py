"""The core's voice: speaks lines through the TTS process, can pause and switch voices."""

import itertools
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from reflektortts.sinks.tts.client import TtsClient, TtsServiceError

logger = logging.getLogger(__name__)


class SpeechClient(Protocol):
    """The part of TtsClient the narrator uses."""

    def say(self, text: str, rate: float, cut_off: bool) -> None: ...

    def stop(self, drop_waiting: bool) -> None: ...

    def close(self) -> None: ...


class Narrator:
    """Speaks lines unless paused, at the chosen rate, each one either cutting off the line being
    spoken or waiting its turn; switching voices starts a new TTS process.

    The TTS process, which loads the voice, runs only between start() and close(), e.g. while a
    app is read; meanwhile the narrator only remembers the voice, and has nothing to say or stop.

    on_speaking is called with True when speech starts after silence and with False when it falls
    silent, across voice switches: an old voice still finishing counts as speaking.
    """

    def __init__(
        self,
        voice: str,
        start_client: Callable[[str, Callable[[bool], None]], SpeechClient] = TtsClient,
        on_speaking: Callable[[bool], None] = lambda active: None,
    ) -> None:
        self._start_client = start_client
        self._on_speaking = on_speaking
        self._lock = threading.Lock()
        self._client_ids = itertools.count()
        self._speaking_lock = threading.Lock()
        self._speaking: set[int] = set()
        """IDs of the clients speaking right now."""
        self._voice = voice
        self._paused = False
        self._rate = 1.0
        self._cut_off = False
        self._client: SpeechClient | None = None

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def paused(self) -> bool:
        return self._paused

    def configure(self, rate: float, cut_off: bool) -> None:
        """Applies from the next line on."""
        with self._lock:
            self._rate = rate
            self._cut_off = cut_off

    def start(self) -> None:
        """Starts the TTS process with the voice, unless it runs already."""
        with self._lock:
            if self._client is None:
                self._client = self._start(self._voice)

    def say(self, text: str) -> None:
        with self._lock:
            if self._client is not None and not self._paused:
                self._client.say(text, self._rate, self._cut_off)

    def stop_line(self) -> None:
        """Cuts off the line being spoken; the next waiting line, or the next line read, follows."""
        with self._lock:
            self._stop(drop_waiting=False)

    def pause(self) -> None:
        """Stops the current line, drops those waiting, and ignores new ones until resume()."""
        with self._lock:
            self._paused = True
            self._stop(drop_waiting=True)

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def use_voice(self, voice: str) -> None:
        """Switches voices; a running TTS process is replaced by one with the new voice."""
        with self._lock:
            if voice == self._voice:
                return
            old_client = self._client
            self._voice = voice
            if old_client is not None:
                self._client = self._start(voice)
        if old_client is not None:
            old_client.close()

    def close(self) -> None:
        """Stops the TTS process; start() starts it again."""
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            client.close()

    def _stop(self, drop_waiting: bool) -> None:
        """Stops speech, if any: a speech process that has died has nothing to stop. That is only
        logged here; the next line spoken reports it to the user."""
        if self._client is None:
            return
        try:
            self._client.stop(drop_waiting)
        except TtsServiceError as error:
            logger.warning("Nothing to stop: %s", error)

    def _start(self, voice: str) -> SpeechClient:
        client_id = next(self._client_ids)
        return self._start_client(voice, lambda active: self._client_speaking(client_id, active))

    def _client_speaking(self, client_id: int, active: bool) -> None:
        with self._speaking_lock:
            was_speaking = bool(self._speaking)
            if active:
                self._speaking.add(client_id)
            else:
                self._speaking.discard(client_id)
            if bool(self._speaking) != was_speaking:
                self._on_speaking(not was_speaking)
