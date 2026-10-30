import threading
from collections.abc import Mapping
from typing import Any

from reflektortts.app import build_routes, read_game
from reflektortts.events import ErrorEvent, TextEvent
from reflektortts.games.detector import ProcessInfo, RunningGame
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.runner import Route
from reflektortts.profiles.model import Game, Match, Profile, SourceSettings, StageSettings


class FixedSource:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.poll_interval = 0.01
        self.text = text
        self.closed = False

    def read(self) -> str | None:
        return self.text

    def close(self) -> None:
        self.closed = True


class Suffix:
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix

    def process(self, event: TextEvent) -> TextEvent | None:
        return TextEvent(event.source, event.text + self.suffix, event.time)


class RecordingSink:
    name = "recorder"

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.received = threading.Event()

    def deliver(self, event: TextEvent) -> None:
        self.texts.append(event.text)
        self.received.set()

    def close(self) -> None:
        pass


def create_source(settings: SourceSettings, game: RunningGame) -> FixedSource:
    if settings.settings.get("broken"):
        raise RuntimeError("This version of the game is not supported")
    return FixedSource(settings.name, settings.settings["text"])


def create_stage(settings: Mapping[str, Any]) -> Suffix:
    return Suffix(settings["suffix"])


SOURCES = {"fixed": SourcePlugin("fixed", {}, create_source)}
STAGES = {"suffix": StagePlugin("suffix", {}, create_stage)}


def game_with(*sources: SourceSettings) -> RunningGame:
    profile = Profile("game", Game("Game", 2000), Match(("game.exe",)), sources)
    return RunningGame(profile, ProcessInfo(42, "game.exe"))


def test_routes_get_their_sources_and_stages_and_broken_sources_are_reported() -> None:
    errors: list[ErrorEvent] = []
    game = game_with(
        SourceSettings("fixed", "broken", 0.25, {"broken": True}),
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {"suffix": "!"}),)),
    )

    routes = build_routes(game, SOURCES, STAGES, errors.append)

    assert len(routes) == 1
    assert routes[0].source.name == "messages"
    assert [type(stage) for stage in routes[0].stages] == [Suffix]
    assert errors == [ErrorEvent("source.error", "broken", "This version of the game is not supported")]


def test_read_game_runs_until_the_game_exits_then_closes_sources() -> None:
    source = FixedSource("messages", "hi")
    sink = RecordingSink()
    running = threading.Event()
    running.set()

    def is_running(pid: int) -> bool:
        if sink.received.is_set():
            running.clear()
        return running.is_set()

    read_game(
        game_with(),
        [Route(source, [Suffix("!")])],
        [sink],
        threading.Event(),
        is_running=is_running,
        check_seconds=0.01,
    )

    assert sink.texts[0] == "hi!"
    assert source.closed


def test_read_game_returns_when_stopped() -> None:
    source = FixedSource("messages", "hi")
    stop = threading.Event()
    stop.set()

    read_game(game_with(), [Route(source)], [], stop, is_running=lambda pid: True, check_seconds=0.01)

    assert source.closed
