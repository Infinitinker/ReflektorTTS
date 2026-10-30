"""Delivers core events to whoever listens, e.g. API clients."""

import logging
import threading
from collections.abc import Callable

from reflektortts.events import ErrorEvent, Status, SubtitleEvent, TextEvent

logger = logging.getLogger(__name__)

Event = TextEvent | SubtitleEvent | ErrorEvent | Status
Listener = Callable[[Event], None]


class EventBus:
    """Thread-safe publish/subscribe. A failing listener is logged and does not affect the others."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Adds a listener and returns a function that removes it."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: Event) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Event listener failed on %r", event)
