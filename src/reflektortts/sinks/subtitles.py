"""The subtitles sink: shows each line over the app for as long as it is spoken, or takes to read."""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from reflektortts.events import SubtitleEvent, TextEvent

SIZES = ("small", "medium", "large")
POSITIONS = ("top", "bottom")
DEFAULT_SIZE = "medium"
DEFAULT_POSITION = "top"
"""Games usually show their own text at the bottom; subtitles at the top leave it visible."""


@dataclass(frozen=True)
class Timing:
    min_seconds: float = 2.0
    characters_per_second: float = 15.0
    """How fast the user reads a line's text, which sets how long the subtitle of a line that is not
    spoken stays, e.g. while speech is paused."""
    hold: float = 1.0
    """How long a subtitle stays after its line has been spoken."""


DEFAULT_TIMING = Timing()


class Subtitles:
    """Publishes each line as a subtitle and hides it once it has been both read and spoken.

    A subtitle stays at least as long as it takes to read, and while the narrator speaks plus a
    moment after. A new line replaces the one shown. Hiding is decided on a thread of its own.
    """

    name = "subtitles"

    def __init__(
        self,
        publish: Callable[[SubtitleEvent], None],
        enabled: bool = False,
        timing: Timing = DEFAULT_TIMING,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._publish = publish
        self._enabled = enabled
        self._timing = timing
        self._clock = clock
        self._changed = threading.Condition()
        self._text = ""
        self._read_until = -math.inf
        self._speaking = False
        self._silent_since = -math.inf
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="subtitles", daemon=True)
        self._thread.start()

    def deliver(self, event: TextEvent) -> None:
        with self._changed:
            if not self._enabled:
                return
            reading = max(self._timing.min_seconds, len(event.text) / self._timing.characters_per_second)
            self._read_until = self._clock() + reading
            self._show(event.text)

    def speaking(self, active: bool) -> None:
        with self._changed:
            if not active and self._speaking:
                self._silent_since = self._clock()
            self._speaking = active
            self._changed.notify()

    def configure(self, enabled: bool) -> None:
        with self._changed:
            self._enabled = enabled
            if not enabled and self._text:
                self._show("")

    def close(self) -> None:
        with self._changed:
            self._closed = True
            if self._text:
                self._show("")
            self._changed.notify()
        self._thread.join()

    def _show(self, text: str) -> None:
        """Publishes text as the subtitle. Called with the lock held, so a hide never overtakes a newer line."""
        self._text = text
        self._publish(SubtitleEvent(text))
        self._changed.notify()

    def _run(self) -> None:
        with self._changed:
            while not self._closed:
                if not self._text or self._speaking:
                    self._changed.wait()
                    continue
                hide_at = max(self._read_until, self._silent_since + self._timing.hold)
                remaining = hide_at - self._clock()
                if remaining > 0:
                    self._changed.wait(remaining)
                else:
                    self._show("")
