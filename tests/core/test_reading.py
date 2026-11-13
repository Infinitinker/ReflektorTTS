"""Reading an app: its routes, and running them until the app exits."""

import threading
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from reflektortts.apps.detector import RunningApp
from reflektortts.core.reading import build_routes, read_app
from reflektortts.events import ErrorEvent, Output
from reflektortts.glossary import Glossaries, GlossaryTerm
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.runner import Chain, Route
from reflektortts.profiles.model import SourceSettings, StageSettings
from tests.core.fake_plugins import SOURCES, STAGES, FixedSource, RecordingSink, Suffix, app_with


def test_routes_get_their_sources_and_stages_and_broken_sources_are_reported() -> None:
    errors: list[ErrorEvent] = []
    app = app_with(
        SourceSettings("fixed", "broken", 0.25, {"broken": True}),
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {"suffix": "!"}),)),
    )

    routes = build_routes(app, SOURCES, STAGES, errors.append)

    assert len(routes) == 1
    assert routes[0].source.name == "messages"
    [text_stage] = routes[0].chains[Output.TEXT].stages
    [speech_stage] = routes[0].chains[Output.SPEECH].stages
    assert isinstance(text_stage, Suffix) and isinstance(speech_stage, Suffix)
    assert text_stage is not speech_stage
    assert errors == [ErrorEvent("source.error", "broken", "This version of the app is not supported")]


def test_stages_are_given_the_profiles_glossary() -> None:
    given: list[Glossaries] = []

    def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Suffix:
        given.append(glossaries)
        return Suffix("")

    glossary = {"en": (GlossaryTerm("Sweet", keep=True),)}
    app = app_with(SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {}),)))
    app = RunningApp(replace(app.profile, glossary=glossary), app.process)

    build_routes(app, SOURCES, {"suffix": StagePlugin("suffix", {}, create)}, lambda error: None)

    assert given == [glossary, glossary]


def test_a_source_whose_stage_cannot_start_is_reported_closed_and_skipped() -> None:
    errors: list[ErrorEvent] = []
    created: list[FixedSource] = []

    def create(settings: SourceSettings, app: RunningApp) -> FixedSource:
        created.append(FixedSource(settings.name, "hi"))
        return created[-1]

    def broken_stage(settings: Mapping[str, Any], glossaries: Glossaries) -> Suffix:
        raise RuntimeError("no rules for this language")

    stages = {"broken": StagePlugin("broken", {}, broken_stage)}
    app = app_with(SourceSettings("fixed", "messages", 0.25, {}, (StageSettings("broken", {}),)))

    routes = build_routes(app, {"fixed": SourcePlugin("fixed", {}, create)}, stages, errors.append)

    assert routes == []
    assert created[0].closed
    assert errors == [
        ErrorEvent("source.error", "messages", "A processing stage cannot start (no rules for this language).")
    ]


def test_read_game_runs_until_the_game_exits_then_closes_sources() -> None:
    source = FixedSource("messages", "hi")
    sink = RecordingSink()
    running = threading.Event()
    running.set()

    def is_running(pid: int) -> bool:
        if sink.received.is_set():
            running.clear()
        return running.is_set()

    read_app(
        app_with(),
        [Route(source, {Output.SPEECH: Chain([Suffix("!")])})],
        {Output.SPEECH: [sink]},
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

    read_app(app_with(), [Route(source)], {}, stop, is_running=lambda pid: True, check_seconds=0.01)

    assert source.closed


def test_build_routes_asks_whether_each_source_and_stage_is_enabled() -> None:
    app = app_with(
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {"suffix": "!"}),))
    )
    asked: list[str] = []

    def stage_switch(key: str, output: Output) -> bool:
        asked.append(f"{key} {output}")
        return False

    def is_source_enabled(name: str) -> bool:
        asked.append(name)
        return False

    routes = build_routes(app, SOURCES, STAGES, lambda error: None, stage_switch, is_source_enabled)

    assert routes[0].chains[Output.TEXT].is_enabled(0) is False
    assert routes[0].is_source_enabled() is False
    assert asked == ["messages/0:suffix text", "messages"]


def test_each_output_starts_with_the_stages_its_profile_starts_on_there() -> None:
    stage = StageSettings("suffix", {"suffix": "!"}, text=False)
    app = app_with(SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (stage,)))

    [route] = build_routes(app, SOURCES, STAGES, lambda error: None)

    assert route.chains[Output.TEXT].is_enabled(0) is False
    assert route.chains[Output.SPEECH].is_enabled(0) is True


def test_a_stage_that_does_nothing_with_the_languages_is_skipped() -> None:
    app = app_with(
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("polish", {"suffix": "!"}),))
    )
    current = [Languages("en", "en")]

    routes = build_routes(app, SOURCES, STAGES, lambda error: None, languages=lambda: current[0])

    assert routes[0].chains[Output.SPEECH].is_enabled(0) is False
    current[0] = Languages("en", "pl")
    assert routes[0].chains[Output.SPEECH].is_enabled(0) is True
