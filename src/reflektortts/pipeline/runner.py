"""Polls sources and moves their text through stages to the sinks."""

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from reflektortts.events import ErrorEvent, Output, TextEvent
from reflektortts.languages import DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE, Languages
from reflektortts.pipeline.protocols import Sink, Source, Stage

logger = logging.getLogger(__name__)


def log_error(error: ErrorEvent) -> None:
    logger.error("%s from %s: %s", error.kind, error.origin, error.message)


def always_enabled(position: int) -> bool:
    return True


def always_on() -> bool:
    return True


@dataclass
class Chain:
    """The stages a source's text passes through for one output, in order. Stages keep state per
    chain, so each output has its own."""

    stages: Sequence[Stage] = ()
    is_enabled: Callable[[int], bool] = always_enabled
    """Whether the stage at a position runs; the user can switch stages off while the app runs."""


@dataclass
class Route:
    """One source and, per output, the stages its text passes through; an output without a chain
    gets the text as read."""

    source: Source
    chains: Mapping[Output, Chain] = field(default_factory=dict)
    is_source_enabled: Callable[[], bool] = always_on
    """Whether the source is read; the user can switch sources off while the app runs."""
    next_poll: float = field(default=0.0, init=False)


class Runner:
    """Polls each route's source on its interval and delivers the results to the sinks: each
    output's to its own sinks, after that output's chain of stages.

    When a source has no text, its stages get an event with empty text, so they can tell
    a line disappeared; empty text is never delivered to sinks. Every event carries the
    input and output languages current when it was read. Switched-off sources are not read
    and switched-off stages are skipped.

    A failing source, stage or sink is reported once through on_error and does not stop
    the others; the runner keeps trying it, and when it works again, logs it and tells
    on_works_again its kind and origin, as they were reported. If it fails again with another
    message before then, on_still_failing gets the new error, so a status can say what is wrong
    now; the error is not reported again, as a message can change on every read (an address).
    """

    def __init__(
        self,
        routes: Sequence[Route],
        sinks: Mapping[Output, Sequence[Sink]],
        on_error: Callable[[ErrorEvent], None] = log_error,
        clock: Callable[[], float] = time.monotonic,
        languages: Callable[[], Languages] = lambda: Languages(DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
        on_works_again: Callable[[str, str], None] = lambda kind, origin: None,
        on_still_failing: Callable[[ErrorEvent], None] = lambda error: None,
    ) -> None:
        self._routes = routes
        self._sinks = sinks
        self._on_error = on_error
        self._on_works_again = on_works_again
        self._on_still_failing = on_still_failing
        self._clock = clock
        self._languages = languages
        self._failing: dict[tuple[str, str], str] = {}
        """The message each failing source, stage or sink, by kind and origin, failed with last."""

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
        languages = self._languages()
        try:
            text = source.read(languages)
        except Exception as error:
            self._failed("source.error", source.name, error)
            return
        self._worked("source.error", source.name)

        # No text still goes through the stages, as empty text, so they see a line disappear.
        event = TextEvent(
            source=source.name,
            text=text or "",
            time=now,
            output_language=languages.output,
            input_language=languages.input,
        )
        for output, sinks in self._sinks.items():
            result = self._process(source.name, route.chains.get(output, Chain()), event)
            if result is not None and result.text:
                self._deliver(result, sinks)

    def _process(self, source: str, chain: Chain, event: TextEvent) -> TextEvent | None:
        """The event after the chain's switched-on stages, or None if one held it back or failed."""
        for position, stage in enumerate(chain.stages):
            if not chain.is_enabled(position):
                continue
            stage_name = f"{source}/{type(stage).__name__}"
            try:
                result = stage.process(event)
            except Exception as error:
                self._failed("stage.error", stage_name, error)
                return None
            self._worked("stage.error", stage_name)
            if result is None:
                return None
            event = result
        return event

    def _deliver(self, event: TextEvent, sinks: Sequence[Sink]) -> None:
        for sink in sinks:
            try:
                sink.deliver(event)
            except Exception as error:
                self._failed("sink.error", sink.name, error)
                continue
            self._worked("sink.error", sink.name)

    def _failed(self, kind: str, origin: str, error: Exception) -> None:
        message = str(error)
        last = self._failing.get((kind, origin))
        if last == message:
            return
        self._failing[(kind, origin)] = message
        if error.__cause__ is not None:
            # The user sees the message; what caused it, as the system or a library put it, is only logged.
            logger.info("%s fails because of: %s", origin, error.__cause__)
        if last is None:
            self._on_error(ErrorEvent(kind, origin, message))
        else:
            logger.debug("%s still fails: %s", origin, message)
            self._on_still_failing(ErrorEvent(kind, origin, message))

    def _worked(self, kind: str, origin: str) -> None:
        if self._failing.pop((kind, origin), None) is not None:
            logger.info("%s works again", origin)
            self._on_works_again(kind, origin)
