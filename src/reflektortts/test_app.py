import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from reflektortts.api.server import StageError
from reflektortts.app import Core, build_routes, read_game
from reflektortts.bus import Event
from reflektortts.events import ErrorEvent, GameInfo, Status, TextEvent
from reflektortts.games.detector import ProcessInfo, RunningGame
from reflektortts.languages import LanguageError, Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.runner import Route
from reflektortts.profiles.model import Game, Match, Profile, SourceSettings, StageSettings
from reflektortts.settings import load_settings
from reflektortts.tts.engine import VoiceError, VoiceInfo
from reflektortts.tts.narrator import Narrator
from reflektortts.tts.test_narrator import Clients


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
STAGES = {"suffix": StagePlugin("suffix", {}, create_stage, summary="adds a suffix")}


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


ADAM = VoiceInfo(id="windows:Microsoft Adam", engine="windows", name="Microsoft Adam", language="pl-PL")
PAULINA = VoiceInfo(id="windows:Microsoft Paulina", engine="windows", name="Microsoft Paulina", language="pl-PL")
LJSPEECH = VoiceInfo(id="piper:en_US-ljspeech-medium", engine="piper", name="en_US-ljspeech-medium", language="en-US")
GTA2 = Profile(
    "grand-theft-auto-2-1999",
    Game("Grand Theft Auto 2", 1999),
    Match(("gta2.exe",)),
    (SourceSettings("fixed", "messages", 0.25, {}, (StageSettings("suffix", {}), StageSettings("suffix", {}))),),
)


def make_core(tmp_path: Path, clients: Clients, voices: list[VoiceInfo] | None = None) -> Core:
    return Core(
        profiles=[GTA2],
        settings_file=tmp_path / "settings.json",
        narrator_factory=lambda voice: Narrator(voice, clients.start),
        list_voices=lambda: [LJSPEECH, ADAM, PAULINA] if voices is None else voices,
        stages=STAGES,
    )


def test_core_saves_a_new_voice_and_remembers_it_for_its_language(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    events: list[Event] = []
    core.subscribe(events.append)

    status = core.set_voice("windows:Microsoft Paulina")

    assert status == Status(
        game=None, voice="windows:Microsoft Paulina", game_language="auto", speech_language="en", paused=False
    )
    assert events == [status]
    saved = load_settings(tmp_path / "settings.json")
    assert saved.voice == "windows:Microsoft Paulina"
    assert saved.voices_by_language == {"pl": "windows:Microsoft Paulina"}
    assert make_core(tmp_path, Clients()).status().voice == "windows:Microsoft Paulina"


def test_core_rejects_voices_that_are_not_available(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    with pytest.raises(VoiceError, match=r'no voice "piper:missing"\. Available: piper:en_US'):
        core.set_voice("piper:missing")


def test_speech_language_switches_to_the_voice_last_used_for_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core.set_voice("windows:Microsoft Paulina")
    core.set_voice("piper:en_US-ljspeech-medium")

    status = core.set_speech_language("pl")

    assert (status.speech_language, status.voice) == ("pl", "windows:Microsoft Paulina")
    assert load_settings(tmp_path / "settings.json").voice == "windows:Microsoft Paulina"


def test_speech_language_without_a_remembered_voice_takes_the_first_that_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    assert core.set_speech_language("pl").voice == "windows:Microsoft Adam"


def test_speech_language_keeps_a_voice_that_already_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core.set_voice("windows:Microsoft Paulina")

    assert core.set_speech_language("pl").voice == "windows:Microsoft Paulina"


def test_speech_language_without_any_voice_keeps_the_current_voice(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients(), voices=[LJSPEECH])

    status = core.set_speech_language("pl")

    assert (status.speech_language, status.voice) == ("pl", "piper:en_US-ljspeech-medium")


def test_languages_are_saved_and_checked(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    core.set_game_language("en")
    core.set_speech_language("pl")

    assert core.languages() == Languages(game="en", speech="pl")
    assert load_settings(tmp_path / "settings.json").game_language == "en"
    with pytest.raises(LanguageError, match='no language "auto"'):
        core.set_speech_language("auto")
    with pytest.raises(LanguageError, match='no language "xx"'):
        core.set_game_language("xx")


def test_pause_resume_and_stop_line(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)

    core.stop_line()
    assert core.set_paused(True).paused is True
    assert clients.started[0].stopped == 2
    assert core.set_paused(False).paused is False


def test_stages_of_the_game_being_read_can_be_switched_off_and_stay_off(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._profile = GTA2

    status = core.set_stage_enabled("messages/1:suffix", False)

    assert [stage.enabled for stage in status.sources[0].stages] == [True, False]
    assert (status.sources[0].stages[0].type, status.sources[0].stages[0].summary) == ("suffix", "adds a suffix")
    assert not core.is_stage_enabled("messages/1:suffix")
    assert load_settings(tmp_path / "settings.json").disabled_stages == {GTA2.id: ["messages/1:suffix"]}
    core.set_stage_enabled("messages/1:suffix", True)
    assert load_settings(tmp_path / "settings.json").disabled_stages == {}


def test_switching_stages_needs_a_game_and_a_known_stage(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    with pytest.raises(StageError, match="No game is being read"):
        core.set_stage_enabled("messages/0:suffix", False)
    core._profile = GTA2
    with pytest.raises(StageError, match='has no stage "messages/9:x"'):
        core.set_stage_enabled("messages/9:x", False)


def test_build_routes_asks_whether_each_stage_is_enabled() -> None:
    game = game_with(
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {"suffix": "!"}),))
    )
    asked: list[str] = []

    def is_enabled(key: str) -> bool:
        asked.append(key)
        return False

    routes = build_routes(game, SOURCES, STAGES, lambda error: None, is_enabled)

    assert routes[0].is_enabled(0) is False
    assert asked == ["messages/0:suffix"]


def test_source_errors_after_the_game_exits_are_not_reported(tmp_path: Path) -> None:
    running = {42}
    core = Core(
        profiles=[],
        settings_file=tmp_path / "settings.json",
        narrator_factory=lambda voice: Narrator(voice, Clients().start),
        list_voices=lambda: [ADAM],
        is_running=lambda pid: pid in running,
        stages=STAGES,
    )
    core._game = GameInfo("Game", 42)
    events: list[Event] = []
    core.subscribe(events.append)

    core._report(ErrorEvent("source.error", "messages", "read failed"))
    running.clear()
    core._report(ErrorEvent("source.error", "messages", "read failed"))

    assert events == [ErrorEvent("source.error", "messages", "read failed")]
