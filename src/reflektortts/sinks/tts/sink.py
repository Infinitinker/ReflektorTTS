"""Sink that speaks text through the TTS service."""

from typing import Protocol

from reflektortts.events import TextEvent


class SpeechService(Protocol):
    """The part of the Narrator the sink uses."""

    def say(self, text: str) -> None: ...

    def close(self) -> None: ...


class TtsSink:
    """Speaks each line; a new line cuts off the one still being spoken."""

    name = "tts"

    def __init__(self, service: SpeechService) -> None:
        self._service = service

    def deliver(self, event: TextEvent) -> None:
        self._service.say(event.text)

    def close(self) -> None:
        self._service.close()
