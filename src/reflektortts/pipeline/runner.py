"""Polls sources and moves their text through stages to the sinks."""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from reflektortts.events import ErrorEvent, TextEvent
from reflektortts.languages import AUTO, DEFAULT_SPEECH_LANGUAGE, Languages
from reflektortts.pipeline.protocols import Sink, Source, Stage

logger = logging.getLogger(__name__)


def log_error(error: ErrorEvent) -> None:
    logger.error("%s from %s: %s", error.kind, error.origin, error.message)


def always_enabled(position: int) -> bool:
    return True


def always_on() -> bool:
    return True


@dataclass
class Route:
    """One source and the stages its text passes through. Stages keep state per route."""

    source: Source
    stages: Sequence[Stage] = ()
    is_enabled: Callable[[int], bool] = always_enabled
    """Whether the stage at a position runs; the player can switch stages off while playing."""
    is_source_enabled: Callable[[], bool] = always_on
    """Whether the source is read; the player can switch sources off while playing."""
    next_poll: float = field(default=0.0, init=False)


class Runner:
    """Polls each route's source on its interval and delivers the results to every sink.

    When a source has no text, its stages get an event with empty text, so they can tell
    a line disappeared; empty text is never delivered to sinks. Every event carries the
    game and speech languages current when it was read. Switched-off sources are not read
    and switched-off stages are skipped.

    A failing source, stage or sink is reported once through on_error and does not stop
    the others; the runner keeps trying it and logs when it works again.
    """

    def __init__(
        self,
        routes: Sequence[Route],
        sinks: Sequence[Sink],
        on_error: Callable[[ErrorEvent], None] = log_error,
        clock: Callable[[], float] = time.monotonic,
        languages: Callable[[], Languages] = lambda: Languages(game=AUTO, speech=DEFAULT_SPEECH_LANGUAGE),
    ) -> None:
        self._routes = routes
        self._sinks = sinks
        self._on_error = on_error
        self._clock = clock
        self._languages = languages
        self._failing: set[tuple[str, str]] = set()

    def run(self, stop: threading.Event) -> None:
        """Polls until stop is set."""
        while not stop.is_set():
            now = self._clock()
            self.poll(now)
            next_poll = min((route.next_poll for route in self._routes), default=now + 1.0)
            stop.wait(max(0.0, next_poll - self._clock()))

    def poll(self, now: float) -> None:
        """Reads every source that is due at time now."""
        for route in self._routes:
            if now >= route.next_poll:
                route.next_poll = now + route.source.poll_interval
                if route.is_source_enabled():
                    self._poll_route(route, now)

    def _poll_route(self, route: Route, now: float) -> None:
        source = route.source
        try:
            text = source.read()
        except Exception as error:
            self._failed("source.error", source.name, error)
            return
        self._worked("source.error", source.name)

        # No text still goes through the stages, as empty text, so they see a line disappear.
        languages = self._languages()
        event = TextEvent(
            source=source.name,
            text=text or "",
            time=now,
            speech_language=languages.speech,
            game_language=languages.game,
        )
        for position, stage in enumerate(route.stages):
            if not route.is_enabled(position):
                continue
            stage_name = f"{source.name}/{type(stage).__name__}"
            try:
                result = stage.process(event)
            except Exception as error:
                self._failed("stage.error", stage_name, error)
                return
            self._worked("stage.error", stage_name)
            if result is None:
                return
            event = result
        if event.text:
            self._deliver(event)

    def _deliver(self, event: TextEvent) -> None:
        for sink in self._sinks:
            try:
                sink.deliver(event)
            except Exception as error:
                self._failed("sink.error", sink.name, error)
                continue
            self._worked("sink.error", sink.name)

    def _failed(self, kind: str, origin: str, error: Exception) -> None:
        if (kind, origin) not in self._failing:
            self._failing.add((kind, origin))
            self._on_error(ErrorEvent(kind, origin, str(error)))

    def _worked(self, kind: str, origin: str) -> None:
        if (kind, origin) in self._failing:
            self._failing.discard((kind, origin))
            logger.info("%s works again", origin)
