"""Lets the user hear a voice: a sample sentence spoken through a TTS process of its own."""

import threading
from collections.abc import Callable

from reflektortts.events import PreviewEvent
from reflektortts.sinks.tts.client import TtsClient
from reflektortts.sinks.tts.narrator import SpeechClient
from reflektortts.tts.service import NewLine


def _in_background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="voice preview", daemon=True).start()


class VoicePreview:
    """Speaks a sample with a voice, apart from the app's narrator: an app being read keeps its
    voice, and its sound is not lowered. The TTS process exits once the sample is spoken; a new
    preview cuts off the one playing.

    on_change hears when a preview starts and when it ends: spoken, or its voice could not be
    loaded. A preview cut off by another one only starts the other.

    Processes are closed in the background: closing waits for the process to exit, and the end of
    a sample is heard on the process's own event thread, which cannot wait for itself.
    """

    def __init__(
        self,
        on_change: Callable[[PreviewEvent], None] = lambda event: None,
        start_client: Callable[[str, Callable[[bool], None], Callable[[], None]], SpeechClient] = TtsClient,
        in_background: Callable[[Callable[[], None]], None] = _in_background,
    ) -> None:
        self._on_change = on_change
        self._start_client = start_client
        self._in_background = in_background
        self._lock = threading.Lock()
        self._client: SpeechClient | None = None

    def play(self, voice: str, text: str) -> None:
        def speaking(active: bool) -> None:
            if not active:
                self._in_background(client.close)

        def exited() -> None:
            with self._lock:
                if self._client is not client:
                    return
                self._client = None
                self._on_change(PreviewEvent(voice, playing=False))

        # Announced under the lock, so a voice that fails at once cannot be heard to end first.
        with self._lock:
            old = self._client
            client = self._client = self._start_client(voice, speaking, exited)
            self._on_change(PreviewEvent(voice, playing=True))
        if old is not None:
            self._in_background(old.close)
        client.say(text, 1.0, NewLine.CUT_OFF)

    def close(self) -> None:
        with self._lock:
            client = self._client
        if client is not None:
            client.close()
