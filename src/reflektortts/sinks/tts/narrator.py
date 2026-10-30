"""The core's voice: speaks lines through the TTS process, can pause and switch voices."""

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
    """Speaks lines unless paused; switching voices starts a new TTS process."""

    def __init__(self, voice: str, start_client: Callable[[str], SpeechClient] = TtsClient) -> None:
        self._start_client = start_client
        self._lock = threading.Lock()
        self._voice = voice
        self._paused = False
        self._client = start_client(voice)

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
            self._client = self._start_client(voice)
            self._voice = voice
        old_client.close()

    def close(self) -> None:
        with self._lock:
            self._client.close()
