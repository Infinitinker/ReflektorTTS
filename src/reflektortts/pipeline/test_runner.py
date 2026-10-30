import threading

import pytest

from reflektortts.events import ErrorEvent, TextEvent
from reflektortts.pipeline.runner import Route, Runner


class ScriptedSource:
    """Returns the next scripted value on each read; an Exception value is raised."""

    def __init__(self, name: str, script: list[str | None | Exception], poll_interval: float = 1.0) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._script = script
        self.reads = 0

    def read(self) -> str | None:
        self.reads += 1
        value = self._script.pop(0) if self._script else None
        if isinstance(value, Exception):
            raise value
        return value

    def close(self) -> None:
        pass


class Upper:
    def process(self, event: TextEvent) -> TextEvent | None:
        return TextEvent(event.source, event.text.upper(), event.time)


class DropShort:
    def process(self, event: TextEvent) -> TextEvent | None:
        return event if len(event.text) > 2 else None


class Exploding:
    def process(self, event: TextEvent) -> TextEvent | None:
        raise ValueError("bad stage")


class RecordingSink:
    def __init__(self, name: str = "recorder", fail_times: int = 0) -> None:
        self.name = name
        self.events: list[TextEvent] = []
        self._fail_times = fail_times

    def deliver(self, event: TextEvent) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise OSError("device gone")
        self.events.append(event)

    def close(self) -> None:
        pass


def texts(sink: RecordingSink) -> list[str]:
    return [event.text for event in sink.events]


def test_text_passes_through_stages_in_order_to_every_sink() -> None:
    first, second = RecordingSink("a"), RecordingSink("b")
    source = ScriptedSource("memory", ["hi", "hello"])
    runner = Runner([Route(source, [DropShort(), Upper()])], [first, second])

    runner.poll(0.0)
    runner.poll(1.0)

    assert texts(first) == texts(second) == ["HELLO"]
    assert first.events[0] == TextEvent("memory", "HELLO", 1.0)


def test_sources_are_read_only_when_due() -> None:
    fast = ScriptedSource("fast", [], poll_interval=0.25)
    slow = ScriptedSource("slow", [], poll_interval=1.0)
    runner = Runner([Route(fast), Route(slow)], [])

    for tick in range(4):
        runner.poll(tick * 0.25)

    assert fast.reads == 4
    assert slow.reads == 1


def test_no_text_delivers_nothing() -> None:
    sink = RecordingSink()
    Runner([Route(ScriptedSource("memory", [None]))], [sink]).poll(0.0)

    assert sink.events == []


def test_failing_source_is_reported_once_and_others_keep_working() -> None:
    errors: list[ErrorEvent] = []
    sink = RecordingSink()
    broken = ScriptedSource("memory", [OSError("game closed"), OSError("game closed"), "back"])
    healthy = ScriptedSource("clipboard", ["a", "b", "c"])
    runner = Runner([Route(broken), Route(healthy)], [sink], on_error=errors.append)

    for tick in range(3):
        runner.poll(float(tick))

    assert errors == [ErrorEvent("source.error", "memory", "game closed")]
    assert texts(sink) == ["a", "b", "back", "c"]


def test_failing_stage_drops_the_event_and_is_reported() -> None:
    errors: list[ErrorEvent] = []
    sink = RecordingSink()
    runner = Runner([Route(ScriptedSource("memory", ["x"]), [Exploding()])], [sink], on_error=errors.append)

    runner.poll(0.0)

    assert sink.events == []
    assert errors == [ErrorEvent("stage.error", "memory/Exploding", "bad stage")]


def test_failing_sink_does_not_block_other_sinks(caplog: pytest.LogCaptureFixture) -> None:
    errors: list[ErrorEvent] = []
    flaky, steady = RecordingSink("tts", fail_times=2), RecordingSink("log")
    runner = Runner([Route(ScriptedSource("memory", ["one", "two", "three"]))], [flaky, steady], errors.append)

    caplog.set_level("INFO")
    for tick in range(3):
        runner.poll(float(tick))

    assert errors == [ErrorEvent("sink.error", "tts", "device gone")]
    assert texts(steady) == ["one", "two", "three"]
    assert texts(flaky) == ["three"]
    assert "tts works again" in caplog.text


class StoppingSource(ScriptedSource):
    """Sets stop after its third read."""

    def __init__(self, stop: threading.Event) -> None:
        super().__init__("memory", [], poll_interval=0.01)
        self._stop = stop

    def read(self) -> str | None:
        if self.reads == 2:
            self._stop.set()
        return super().read()


def test_run_polls_until_stopped() -> None:
    stop = threading.Event()
    source = StoppingSource(stop)
    worker = threading.Thread(target=Runner([Route(source)], []).run, args=(stop,))
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert source.reads == 3
