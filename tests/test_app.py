import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from reflektortts.api.server import SourceError, StageError
from reflektortts.app import Core, build_routes, read_game
from reflektortts.bus import Event
from reflektortts.ducking.records import DuckRecords
from reflektortts.ducking.volume import OpenAppVolume
from reflektortts.events import ErrorEvent, GameInfo, Status, TextEvent
from reflektortts.games.detector import ProcessInfo, RunningGame
from reflektortts.languages import LanguageError, Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.runner import Route
from reflektortts.profiles.model import Game, Match, Profile, SourceSettings, StageSettings
from reflektortts.settings import GameSettings, load_game, load_shared
from reflektortts.sinks.tts.narrator import Narrator
from reflektortts.tts.engine import DEFAULT_VOICE, VoiceError, VoiceInfo
from tests.sinks.tts.test_narrator import Clients


class FixedSource:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.poll_interval = 0.01
        self.text = text
        self.closed = False

    def read(self, languages: Languages) -> str | None:
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
STAGES = {
    "suffix": StagePlugin("suffix", {}, create_stage, summary="adds a suffix"),
    "polish": StagePlugin(
        "polish",
        {},
        create_stage,
        inactive_reason=lambda languages: None if languages.output == "pl" else "Only Polish",
    ),
}


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


MAD_MAX = Profile("mad-max-2015", Game("Mad Max", 2015), Match(("MadMax.exe",)))


def no_sound() -> OpenAppVolume:
    return lambda pid: None


def playing(profile: Profile) -> RunningGame:
    return RunningGame(profile, ProcessInfo(42, profile.match.processes[0]))


def saved_for(tmp_path: Path, profile: Profile) -> GameSettings:
    """What is saved for a game, or the defaults if nothing is."""
    return load_game(tmp_path, profile.id)


def make_core(tmp_path: Path, clients: Clients, voices: list[VoiceInfo] | None = None) -> Core:
    return Core(
        profiles=[GTA2],
        settings_dir=tmp_path,
        narrator_factory=lambda voice, on_speaking: Narrator(voice, clients.start, on_speaking),
        list_voices=lambda: [LJSPEECH, ADAM, PAULINA] if voices is None else voices,
        stages=STAGES,
        open_app_volume=no_sound,
        duck_records=DuckRecords(tmp_path / "lowered-games.json"),
    )


def test_a_new_voice_is_saved_for_the_game_and_remembered_for_its_language(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    events: list[Event] = []
    core.subscribe(events.append)

    status = core.set_voice("windows:Microsoft Paulina")

    assert status.voice == "windows:Microsoft Paulina"
    assert events == [status]
    assert saved_for(tmp_path, GTA2).voice == "windows:Microsoft Paulina"
    assert load_shared(tmp_path).voices_by_language == {"pl": "windows:Microsoft Paulina"}


def test_without_a_game_the_defaults_apply_and_changes_are_not_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    status = core.set_speech(1.5, False)

    assert status == Status(
        game=None,
        voice=DEFAULT_VOICE,
        game_language="en",
        output_language="en",
        paused=False,
        ducking=True,
        duck_volume=0.3,
        speech_rate=1.5,
        cut_off_lines=False,
        subtitles=False,
        subtitle_size="medium",
        subtitle_position="top",
    )
    assert not (tmp_path / "games").exists()
    assert make_core(tmp_path, Clients()).status().speech_rate == 1.0


def test_core_rejects_voices_that_are_not_available(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    with pytest.raises(VoiceError, match=r'no voice "piper:missing"\. Available: piper:en_US'):
        core.set_voice("piper:missing")


def test_output_language_switches_to_the_voice_last_used_for_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core.set_voice("windows:Microsoft Paulina")
    core.set_voice("piper:en_US-ljspeech-medium")

    status = core.set_output_language("pl")

    assert (status.output_language, status.voice) == ("pl", "windows:Microsoft Paulina")


def test_output_language_without_a_remembered_voice_takes_the_first_that_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    assert core.set_output_language("pl").voice == "windows:Microsoft Adam"


def test_output_language_keeps_a_voice_that_already_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core.set_voice("windows:Microsoft Paulina")

    assert core.set_output_language("pl").voice == "windows:Microsoft Paulina"


def test_output_language_without_any_voice_keeps_the_current_voice(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients(), voices=[LJSPEECH])

    status = core.set_output_language("pl")

    assert (status.output_language, status.voice) == ("pl", "piper:en_US-ljspeech-medium")


def test_languages_are_saved_and_checked(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    core.set_game_language("pl")
    core.set_output_language("pl")

    assert core.languages() == Languages(game="pl", output="pl")
    saved = saved_for(tmp_path, GTA2)
    assert (saved.game_language, saved.output_language) == ("pl", "pl")
    with pytest.raises(LanguageError, match='no language "auto"'):
        core.set_output_language("auto")
    with pytest.raises(LanguageError, match='no language "auto"'):
        core.set_game_language("auto")


def test_ducking_settings_are_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    status = core.set_ducking(False, 0.5)

    assert (status.ducking, status.duck_volume) == (False, 0.5)
    saved = saved_for(tmp_path, GTA2)
    assert (saved.ducking, saved.duck_volume) == (False, 0.5)
    core.close()


def test_speech_settings_are_saved_and_used_for_the_next_line(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(GTA2))

    status = core.set_speech(1.5, True)
    core._narrator.say("hi")

    assert (status.speech_rate, status.cut_off_lines) == (1.5, True)
    saved = saved_for(tmp_path, GTA2)
    assert (saved.speech_rate, saved.cut_off_lines) == (1.5, True)
    assert clients.started[0].how == [(1.5, True)]
    core.close()


def test_subtitle_settings_are_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    status = core.set_subtitles(True, "large", "bottom")

    assert (status.subtitles, status.subtitle_size, status.subtitle_position) == (True, "large", "bottom")
    saved = saved_for(tmp_path, GTA2)
    assert (saved.subtitles, saved.subtitle_size, saved.subtitle_position) == (True, "large", "bottom")
    core.close()


def test_pause_resume_and_stop_line(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(GTA2))

    core.stop_line()
    assert core.set_paused(True).paused is True
    assert clients.started[0].stopped == 2
    assert core.set_paused(False).paused is False


def test_stages_of_the_game_being_read_can_be_switched_off_and_stay_off(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    status = core.set_stage_enabled("messages/1:suffix", False)

    assert [stage.enabled for stage in status.sources[0].stages] == [True, False]
    assert (status.sources[0].stages[0].type, status.sources[0].stages[0].summary) == ("suffix", "adds a suffix")
    assert not core.is_stage_enabled("messages/1:suffix")
    assert saved_for(tmp_path, GTA2).disabled_stages == ("messages/1:suffix",)
    core.set_stage_enabled("messages/1:suffix", True)
    assert saved_for(tmp_path, GTA2).disabled_stages == ()


def test_switching_stages_needs_a_game_and_a_known_stage(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    with pytest.raises(StageError, match="No game is being read"):
        core.set_stage_enabled("messages/0:suffix", False)
    core._enter(playing(GTA2))
    with pytest.raises(StageError, match='has no stage "messages/9:x"'):
        core.set_stage_enabled("messages/9:x", False)


def test_sources_of_the_game_being_read_can_be_switched_off_and_stay_off(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    status = core.set_source_enabled("messages", False)

    assert (status.sources[0].type, status.sources[0].enabled) == ("fixed", False)
    assert not core.is_source_enabled("messages")
    assert saved_for(tmp_path, GTA2).disabled_sources == ("messages",)
    core.set_source_enabled("messages", True)
    assert saved_for(tmp_path, GTA2).disabled_sources == ()
    with pytest.raises(SourceError, match='has no source "signs"'):
        core.set_source_enabled("signs", False)


def test_each_game_keeps_its_own_settings(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(MAD_MAX))
    core.set_output_language("pl")
    core.set_speech(1.5, False)
    core._leave()
    core._enter(playing(GTA2))
    core.set_speech(0.8, False)
    core._leave()

    core._enter(playing(MAD_MAX))

    assert (core.status().output_language, core.status().speech_rate) == ("pl", 1.5)
    assert core.status().voice == "windows:Microsoft Adam"
    assert saved_for(tmp_path, GTA2).speech_rate == 0.8


def test_a_game_played_for_the_first_time_starts_with_the_defaults(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    core.set_game_language("pl")
    core.set_voice("windows:Microsoft Paulina")
    core.set_source_enabled("messages", False)
    core._leave()

    core._enter(playing(MAD_MAX))

    status = core.status()
    assert (status.game_language, status.voice) == ("en", DEFAULT_VOICE)
    assert core.is_source_enabled("messages")
    assert not (tmp_path / "games" / f"{MAD_MAX.id}.json").exists()


def test_a_voice_is_loaded_only_while_a_game_is_read(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(MAD_MAX))
    core.set_output_language("pl")
    core._leave()
    assert [client.voice for client in clients.started] == [DEFAULT_VOICE, "windows:Microsoft Adam"]

    core._enter(playing(MAD_MAX))

    assert [client.voice for client in clients.started][-1] == "windows:Microsoft Adam"
    assert len(clients.started) == 3
    assert all(client.closed for client in clients.started[:2])


def test_no_voice_is_loaded_while_waiting_for_a_game(tmp_path: Path) -> None:
    clients = Clients()
    make_core(tmp_path, clients)

    assert clients.started == []


def test_the_defaults_apply_again_once_the_game_closes(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    core.set_game_language("pl")

    core._leave()

    assert core.status().game_language == "en"


def test_build_routes_asks_whether_each_source_and_stage_is_enabled() -> None:
    game = game_with(
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("suffix", {"suffix": "!"}),))
    )
    asked: list[str] = []

    def is_enabled(key: str) -> bool:
        asked.append(key)
        return False

    routes = build_routes(game, SOURCES, STAGES, lambda error: None, is_enabled, is_enabled)

    assert routes[0].is_enabled(0) is False
    assert routes[0].is_source_enabled() is False
    assert asked == ["messages/0:suffix", "messages"]


def test_a_stage_that_does_nothing_with_the_languages_is_skipped() -> None:
    game = game_with(
        SourceSettings("fixed", "messages", 0.25, {"text": "hi"}, (StageSettings("polish", {"suffix": "!"}),))
    )
    current = [Languages("en", "en")]

    routes = build_routes(game, SOURCES, STAGES, lambda error: None, languages=lambda: current[0])

    assert routes[0].is_enabled(0) is False
    current[0] = Languages("en", "pl")
    assert routes[0].is_enabled(0) is True


def test_the_status_says_why_a_stage_does_nothing_and_keeps_its_tick(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(game_with(SourceSettings("fixed", "messages", 0.25, {}, (StageSettings("polish", {}),))))

    stage = core.status().sources[0].stages[0]
    assert (stage.enabled, stage.inactive) == (True, "Only Polish")

    stage = core.set_output_language("pl").sources[0].stages[0]
    assert (stage.enabled, stage.inactive) == (True, None)


def core_playing(tmp_path: Path, is_running: Callable[[int], bool], exit_grace_seconds: float) -> Core:
    core = Core(
        profiles=[],
        settings_dir=tmp_path,
        narrator_factory=lambda voice, on_speaking: Narrator(voice, Clients().start, on_speaking),
        list_voices=lambda: [ADAM],
        is_running=is_running,
        stages=STAGES,
        open_app_volume=no_sound,
        duck_records=DuckRecords(tmp_path / "lowered-games.json"),
        exit_grace_seconds=exit_grace_seconds,
    )
    core._game = GameInfo("Game", 42)
    return core


def test_source_errors_after_the_game_exits_are_not_reported(tmp_path: Path) -> None:
    running = {42}
    core = core_playing(tmp_path, lambda pid: pid in running, exit_grace_seconds=0)
    events: list[Event] = []
    core.subscribe(events.append)

    core._report(ErrorEvent("source.error", "messages", "read failed"))
    running.clear()
    core._report(ErrorEvent("source.error", "messages", "read failed"))

    assert events == [ErrorEvent("source.error", "messages", "read failed")]


def test_source_errors_while_the_game_is_exiting_are_not_reported(tmp_path: Path) -> None:
    # The process still counts as running for a moment after its memory is gone.
    checks = iter([True, True])
    core = core_playing(tmp_path, lambda pid: next(checks, False), exit_grace_seconds=5)
    events: list[Event] = []
    core.subscribe(events.append)

    core._report(ErrorEvent("source.error", "messages", "read failed"))

    assert events == []
