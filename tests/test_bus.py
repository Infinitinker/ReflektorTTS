import pytest

from reflektortts.bus import Event, EventBus
from reflektortts.events import TextEvent


def test_events_reach_every_listener_until_it_unsubscribes() -> None:
    bus = EventBus()
    first: list[Event] = []
    second: list[Event] = []
    bus.subscribe(first.append)
    unsubscribe = bus.subscribe(second.append)

    bus.publish(TextEvent("memory", "one", 0.0))
    unsubscribe()
    bus.publish(TextEvent("memory", "two", 1.0))

    assert [event.text for event in first if isinstance(event, TextEvent)] == ["one", "two"]
    assert [event.text for event in second if isinstance(event, TextEvent)] == ["one"]


def test_failing_listener_does_not_stop_the_others(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    received: list[Event] = []

    def broken(event: Event) -> None:
        raise RuntimeError("listener bug")

    bus.subscribe(broken)
    bus.subscribe(received.append)
    bus.publish(TextEvent("memory", "hi", 0.0))

    assert len(received) == 1
    assert "Event listener failed" in caplog.text
