from reflektortts.events import TextEvent
from reflektortts.sinks.tts.sink import TtsSink


class RecordingService:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.closed = False

    def say(self, text: str) -> None:
        self.said.append(text)

    def close(self) -> None:
        self.closed = True


def test_delivered_text_is_spoken_and_close_stops_the_service() -> None:
    service = RecordingService()
    sink = TtsSink(service)

    sink.deliver(TextEvent("memory", "Hello", 0.0))
    sink.close()

    assert service.said == ["Hello"]
    assert service.closed
