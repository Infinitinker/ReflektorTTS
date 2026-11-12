"""The core's side of the TTS service: the speaking events it passes on, the service's exit, and its process's log."""

import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, cast

import pytest

from reflektortts.sinks.tts import client
from reflektortts.sinks.tts.client import TtsClient, receive_events
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


class FakeProcess:
    def __init__(self, target: object, args: tuple[Any, ...], name: str, daemon: bool) -> None:
        self.args = args

    def start(self) -> None:
        """Nothing runs; the client's ends of the pipes see the service's ends closed."""


class FakeContext:
    def __init__(self) -> None:
        self.processes: list[FakeProcess] = []

    def Pipe(self, duplex: bool = True) -> tuple[Any, Any]:
        """Real pipes, whose class differs by system (PipeConnection on Windows)."""
        return multiprocessing.Pipe(duplex)

    def Process(self, target: object, args: tuple[Any, ...], name: str, daemon: bool) -> FakeProcess:
        self.processes.append(FakeProcess(target, args, name, daemon))
        return self.processes[-1]


@pytest.mark.parametrize(
    ("log_dir", "names", "log_file"),
    [
        (Path("logs"), {}, Path("logs/reflektortts-tts.log")),
        (Path("logs"), {"log_name": "reflektortts-preview.log"}, Path("logs/reflektortts-preview.log")),
        (None, {}, None),
    ],
)
def test_the_process_logs_to_its_own_file_when_the_core_logs_to_files(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path | None, names: dict[str, Any], log_file: Path | None
) -> None:
    context = FakeContext()
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: context)
    monkeypatch.setattr(client, "file_log_dir", lambda: log_dir)

    TtsClient("piper:a", **names)

    assert context.processes[0].args[-1] == log_file
