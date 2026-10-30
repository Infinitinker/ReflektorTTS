"""Sink that publishes each finished line on the event bus, e.g. for the overlay."""

from reflektortts.bus import EventBus
from reflektortts.events import TextEvent


class BusSink:
    name = "events"

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def deliver(self, event: TextEvent) -> None:
        self._bus.publish(event)

    def close(self) -> None:
        pass
