import threading
from collections.abc import Callable

import pytest

from reflektortts.events import ErrorEvent, Output, TextEvent
from reflektortts.languages import Languages
from reflektortts.pipeline.protocols import Sink, Stage
from reflektortts.pipeline.runner import Chain, Route, Runner, always_enabled


class ScriptedSource:
    """Returns the next scripted value on each read; an Exception value is raised."""

    def __init__(self, name: str, script: list[str | None | Exception], poll_interval: float = 1.0) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self._script = script
        self.reads = 0
        self.languages: list[Languages] = []

    def read(self, languages: Languages) -> str | None:
        self.reads += 1
        self.languages.append(languages)
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


def shown(*stages: Stage, is_enabled: Callable[[int], bool] = always_enabled) -> dict[Output, Chain]:
    """Chains with these stages for the text shown."""
    return {Output.TEXT: Chain(stages, is_enabled)}


def to_text(*sinks: Sink) -> dict[Output, list[Sink]]:
    return {Output.TEXT: list(sinks)}


def test_text_passes_through_stages_in_order_to_every_sink() -> None:
    first, second = RecordingSink("a"), RecordingSink("b")
    source = ScriptedSource("memory", ["hi", "hello"])
    runner = Runner([Route(source, shown(DropShort(), Upper()))], to_text(first, second))

    runner.poll(0.0)
    runner.poll(1.0)

    assert texts(first) == texts(second) == ["HELLO"]
    assert first.events[0] == TextEvent("memory", "HELLO", 1.0)


def test_each_output_has_its_own_chain_and_sinks() -> None:
    text, speech = RecordingSink("subtitles"), RecordingSink("tts")
    chains = {Output.TEXT: Chain([DropShort()]), Output.SPEECH: Chain([Upper()])}
    source = ScriptedSource("memory", ["hi", "hello"])
    runner = Runner([Route(source, chains)], {Output.TEXT: [text], Output.SPEECH: [speech]})

    runner.poll(0.0)
    runner.poll(1.0)

    assert texts(text) == ["hello"]
    assert texts(speech) == ["HI", "HELLO"]


def test_an_output_without_a_chain_gets_the_text_as_read() -> None:
    speech = RecordingSink("tts")
    runner = Runner([Route(ScriptedSource("memory", ["hi"]), shown(Upper()))], {Output.SPEECH: [speech]})

    runner.poll(0.0)

    assert texts(speech) == ["hi"]


def test_events_carry_the_languages_current_when_read() -> None:
    sink = RecordingSink()
    current = [Languages(input="pl", output="en")]
    runner = Runner([Route(ScriptedSource("memory", ["one", "two"]))], to_text(sink), languages=lambda: current[0])

    runner.poll(0.0)
    current[0] = Languages(input="en", output="pl")
    runner.poll(1.0)

    assert [(event.input_language, event.output_language) for event in sink.events] == [("pl", "en"), ("en", "pl")]


def test_sources_read_with_the_players_languages() -> None:
    source = ScriptedSource("subtitles", ["one"])
    Runner([Route(source)], {}, languages=lambda: Languages(input="pl", output="en")).poll(0.0)

    assert source.languages == [Languages(input="pl", output="en")]


def test_switched_off_stages_are_skipped() -> None:
    sink = RecordingSink()
    enabled = {0: True, 1: False}
    route = Route(
        ScriptedSource("memory", ["hello", "hello"]), shown(Upper(), DropShort(), is_enabled=enabled.__getitem__)
    )
    runner = Runner([route], to_text(sink))

    runner.poll(0.0)
    enabled[0] = False
    runner.poll(1.0)

    assert texts(sink) == ["HELLO", "hello"]


def test_switched_off_sources_are_not_read() -> None:
    sink = RecordingSink()
    source = ScriptedSource("memory", ["one", "two"])
    on = [False]
    runner = Runner([Route(source, is_source_enabled=lambda: on[0])], to_text(sink))

    runner.poll(0.0)
    on[0] = True
    runner.poll(1.0)

    assert source.reads == 1
    assert texts(sink) == ["one"]


def test_sources_are_read_only_when_due() -> None:
    fast = ScriptedSource("fast", [], poll_interval=0.25)
    slow = ScriptedSource("slow", [], poll_interval=1.0)
    runner = Runner([Route(fast), Route(slow)], {})

    for tick in range(4):
        runner.poll(tick * 0.25)

    assert fast.reads == 4
    assert slow.reads == 1


class Recording:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def process(self, event: TextEvent) -> TextEvent | None:
        self.texts.append(event.text)
        return event


def test_no_text_reaches_stages_as_empty_text_but_never_sinks() -> None:
    sink, stage = RecordingSink(), Recording()
    Runner([Route(ScriptedSource("memory", [None]), shown(stage))], to_text(sink)).poll(0.0)

    assert stage.texts == [""]
    assert sink.events == []


def test_failing_source_is_reported_once_and_others_keep_working() -> None:
    errors: list[ErrorEvent] = []
    sink = RecordingSink()
    broken = ScriptedSource("memory", [OSError("app closed"), OSError("app closed"), "back"])
    healthy = ScriptedSource("clipboard", ["a", "b", "c"])
    working: list[tuple[str, str]] = []
    runner = Runner(
        [Route(broken), Route(healthy)],
        to_text(sink),
        on_error=errors.append,
        on_works_again=lambda kind, origin: working.append((kind, origin)),
    )

    for tick in range(3):
        runner.poll(float(tick))

    assert errors == [ErrorEvent("source.error", "memory", "app closed")]
    assert working == [("source.error", "memory")]
    assert texts(sink) == ["a", "b", "back", "c"]


def test_a_source_failing_for_another_reason_is_reported_as_still_failing() -> None:
    errors: list[ErrorEvent] = []
    still: list[ErrorEvent] = []
    script: list[str | None | Exception] = [
        OSError("No subtitles for A."),
        OSError("No subtitles for A."),
        OSError("No subtitles for B."),
        "back",
        OSError("No subtitles for B."),
    ]
    runner = Runner(
        [Route(ScriptedSource("vlc", script))], to_text(RecordingSink()), errors.append, on_still_failing=still.append
    )

    for tick in range(5):
        runner.poll(float(tick))

    assert errors == [
        ErrorEvent("source.error", "vlc", "No subtitles for A."),
        ErrorEvent("source.error", "vlc", "No subtitles for B."),
    ]
    assert still == [ErrorEvent("source.error", "vlc", "No subtitles for B.")]


def test_failing_stage_drops_the_event_and_is_reported() -> None:
    errors: list[ErrorEvent] = []
    sink = RecordingSink()
    runner = Runner([Route(ScriptedSource("memory", ["x"]), shown(Exploding()))], to_text(sink), on_error=errors.append)

    runner.poll(0.0)

    assert sink.events == []
    assert errors == [ErrorEvent("stage.error", "memory/Exploding", "bad stage")]


def test_failing_sink_does_not_block_other_sinks(caplog: pytest.LogCaptureFixture) -> None:
    errors: list[ErrorEvent] = []
    flaky, steady = RecordingSink("tts", fail_times=2), RecordingSink("log")
    runner = Runner([Route(ScriptedSource("memory", ["one", "two", "three"]))], to_text(flaky, steady), errors.append)

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

    def read(self, languages: Languages) -> str | None:
        if self.reads == 2:
            self._stop.set()
        return super().read(languages)


def test_run_polls_until_stopped() -> None:
    stop = threading.Event()
    source = StoppingSource(stop)
    worker = threading.Thread(target=Runner([Route(source)], {}).run, args=(stop,))
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert source.reads == 3
