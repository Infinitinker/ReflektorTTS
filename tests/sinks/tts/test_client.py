from multiprocessing.connection import Connection
from typing import cast

from reflektortts.sinks.tts.client import receive_events
from reflektortts.tts.service import Speaking


class FakeEvents:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages
        self.closed = False

    def recv(self) -> object:
        if not self._messages:
            raise EOFError
        return self._messages.pop(0)

    def close(self) -> None:
        self.closed = True


def test_speaking_events_are_passed_on() -> None:
    events = FakeEvents([Speaking(True), "garbage", Speaking(False)])
    reported: list[bool] = []

    receive_events(cast(Connection, events), reported.append)

    assert reported == [True, False]
    assert events.closed


def test_a_service_that_exits_mid_line_counts_as_silent() -> None:
    reported: list[bool] = []

    receive_events(cast(Connection, FakeEvents([Speaking(True)])), reported.append)

    assert reported == [True, False]


def test_the_exit_is_reported_after_the_last_event() -> None:
    reported: list[object] = []

    receive_events(cast(Connection, FakeEvents([Speaking(True)])), reported.append, lambda: reported.append("exited"))

    assert reported == [True, False, "exited"]
