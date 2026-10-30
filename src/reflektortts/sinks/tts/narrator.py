"""The core's voice: speaks lines through the TTS process, can pause and switch voices."""

import itertools
import threading
from collections.abc import Callable
from typing import Protocol

from reflektortts.sinks.tts.client import TtsClient


class SpeechClient(Protocol):
    """The part of TtsClient the narrator uses."""

    def say(self, text: str) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class Narrator:
    """Speaks lines unless paused; switching voices starts a new TTS process.

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
        self._client = self._start(voice)

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def paused(self) -> bool:
        return self._paused

    def say(self, text: str) -> None:
        with self._lock:
            if not self._paused:
                self._client.say(text)

    def stop_line(self) -> None:
        """Cuts off the line being spoken; the next line is spoken as usual."""
        with self._lock:
            self._client.stop()

    def pause(self) -> None:
        """Stops the current line and ignores new ones until resume()."""
        with self._lock:
            self._paused = True
            self._client.stop()

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def use_voice(self, voice: str) -> None:
        with self._lock:
            if voice == self._voice:
                return
            old_client = self._client
            self._client = self._start(voice)
            self._voice = voice
        old_client.close()

    def close(self) -> None:
        with self._lock:
            self._client.close()

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
