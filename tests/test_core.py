import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from reflektortts.api.server import BrokenProfileError, SourceError, StageError, UnknownProfileError
from reflektortts.apps.detector import ProcessInfo, RunningApp
from reflektortts.bus import Event
from reflektortts.core import Core, build_routes, read_app
from reflektortts.ducking.records import DuckRecords
from reflektortts.ducking.volume import OpenAppVolume
from reflektortts.events import (
    AppInfo,
    DownloadEvent,
    ErrorEvent,
    Output,
    ProfileSettingsView,
    Status,
    TextEvent,
    UnsupportedApp,
)
from reflektortts.glossary import Glossaries, GlossaryTerm
from reflektortts.languages import LanguageError, Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.pipeline.runner import Chain, Route
from reflektortts.profiles.catalog import CatalogEntry, Origin, ProfileFiles, ProfileState, ProfileStore
from reflektortts.profiles.loader import PluginSchemas
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings, StageSettings
from reflektortts.settings import ProfileSettings, SettingsChange, load_profile_settings, load_shared
from reflektortts.sinks.tts.narrator import Narrator
from reflektortts.sinks.tts.preview import VoicePreview
from reflektortts.tts.engine import DEFAULT_VOICE, VoiceError, VoiceInfo
from reflektortts.tts.service import NewLine
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


def create_source(settings: SourceSettings, app: RunningApp) -> FixedSource:
    if settings.settings.get("broken"):
        raise RuntimeError("This version of the app is not supported")
    return FixedSource(settings.name, settings.settings["text"])


def create_stage(settings: Mapping[str, Any], glossaries: Glossaries) -> Suffix:
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


def app_with(*sources: SourceSettings) -> RunningApp:
    profile = Profile("app", App("App", 2000), Match((Executable("app.exe"),)), sources)
    return RunningApp(profile, ProcessInfo(42, "app.exe"))


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


ADAM = VoiceInfo("windows:Microsoft Adam", "windows", "Microsoft Adam", "pl-PL", "Windows")
PAULINA = VoiceInfo("windows:Microsoft Paulina", "windows", "Microsoft Paulina", "pl-PL", "Windows")
LJSPEECH = VoiceInfo("piper:en_US-ljspeech-medium", "piper", "en_US-ljspeech-medium", "en-US", "Piper")
GTA2 = Profile(
    "grand-theft-auto-2-1999",
    App("Grand Theft Auto 2", 1999),
    Match((Executable("gta2.exe"),)),
    (SourceSettings("fixed", "messages", 0.25, {}, (StageSettings("suffix", {}), StageSettings("suffix", {}))),),
)


MAD_MAX = Profile("mad-max-2015", App("Mad Max", 2015), Match((Executable("MadMax.exe"),)))


def no_sound() -> OpenAppVolume:
    return lambda pid: None


def playing(profile: Profile) -> RunningApp:
    return RunningApp(profile, ProcessInfo(42, profile.match.executables[0].name))


def saved_for(tmp_path: Path, profile: Profile) -> ProfileSettings:
    """What is saved for an app, or the defaults if nothing is."""
    return load_profile_settings(tmp_path, profile.id)


class FixedProfiles:
    """Bundled profiles that need no files; adding, copying and removing are not used here."""

    def __init__(self, *profiles: Profile) -> None:
        self.catalog = [
            CatalogEntry(profile.id, Origin.BUNDLED, Path(f"{profile.id}.json"), profile) for profile in profiles
        ]

    def load(self) -> list[CatalogEntry]:
        return self.catalog

    def add(self, profile_id: str, data: Any, replace: bool) -> Path:
        raise NotImplementedError

    def copy(self, profile_id: str) -> Path:
        raise NotImplementedError

    def remove(self, profile_id: str) -> None:
        raise NotImplementedError


def make_core(
    tmp_path: Path,
    clients: Clients,
    voices: list[VoiceInfo] | None = None,
    previews: Clients | None = None,
    profiles: ProfileFiles | None = None,
) -> Core:
    return Core(
        profiles=profiles or FixedProfiles(GTA2),
        settings_dir=tmp_path,
        narrator_factory=lambda voice, on_speaking: Narrator(voice, clients.start, on_speaking),
        list_voices=lambda: [LJSPEECH, ADAM, PAULINA] if voices is None else voices,
        stages=STAGES,
        open_app_volume=no_sound,
        duck_records=DuckRecords(tmp_path / "lowered-apps.json"),
        download_sources={},
        preview_factory=lambda on_change: VoicePreview(on_change, (previews or Clients()).start, lambda work: work()),
    )


def change(core: Core, profile: Profile = GTA2, **fields: Any) -> ProfileSettingsView:
    return core.change_profile_settings(profile.id, SettingsChange(**fields))


def test_a_voice_chosen_for_the_app_being_read_is_used_saved_and_remembered_for_its_language(
    tmp_path: Path,
) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(GTA2))
    change(core, output_language="pl")
    events: list[Event] = []
    core.subscribe(events.append)

    view = change(core, voice=PAULINA.id)

    assert (view.profile, view.app_title, view.running, view.voice) == (GTA2.id, "Grand Theft Auto 2", True, PAULINA.id)
    assert core.status().voice == PAULINA.id
    assert clients.started[-1].voice == PAULINA.id and not clients.started[-1].closed
    assert events == [core.status(), view]
    assert saved_for(tmp_path, GTA2).voice == PAULINA.id
    assert load_shared(tmp_path).voices_by_language == {"pl": PAULINA.id}


def test_a_profile_whose_app_does_not_run_is_changed_and_saved_but_nothing_is_applied(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    events: list[Event] = []
    core.subscribe(events.append)

    view = change(core, speech_rate=1.5, output_language="pl")

    assert (view.running, view.speech_rate, view.output_language, view.voice) == (False, 1.5, "pl", ADAM.id)
    assert events == [view]
    assert core.profile_settings(GTA2.id) == view
    saved = saved_for(tmp_path, GTA2)
    assert (saved.speech_rate, saved.output_language, saved.voice) == (1.5, "pl", ADAM.id)
    assert (core.status().speech_rate, core.status().output_language) == (1.0, "en")
    assert clients.started == []
    core._enter(playing(GTA2))
    assert (core.status().speech_rate, core.status().voice) == (1.5, ADAM.id)


def test_without_an_app_the_status_shows_the_defaults(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    assert core.status() == Status(
        app=None,
        voice=DEFAULT_VOICE,
        input_language="en",
        output_language="en",
        paused=False,
        ducking=True,
        duck_volume=0.3,
        speech_rate=1.0,
        new_line="wait",
        subtitles=False,
        subtitle_size="medium",
        subtitle_position="top",
    )


def test_the_status_names_the_profile_of_the_app_being_read(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    core._enter(playing(GTA2))

    assert core.status().app == AppInfo("Grand Theft Auto 2", 42, GTA2.id)


def test_a_profile_s_settings_are_shown_with_its_sources_also_before_its_app_runs(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    view = core.profile_settings(GTA2.id)

    assert (view.running, view.voice, view.output_language) == (False, DEFAULT_VOICE, "en")
    assert [(source.source, source.enabled) for source in view.sources] == [("messages", True)]
    assert [stage.key for stage in view.sources[0].stages] == ["messages/0:suffix", "messages/1:suffix"]
    assert not (tmp_path / "settings" / "profiles").exists()


def test_unknown_and_broken_profiles_have_no_settings(tmp_path: Path) -> None:
    profiles = FixedProfiles(GTA2)
    error = "broken-2000.json: must contain a JSON object."
    profiles.catalog.append(CatalogEntry("broken-2000", Origin.CUSTOM, Path("broken-2000.json"), None, error))
    core = make_core(tmp_path, Clients(), profiles=profiles)

    with pytest.raises(UnknownProfileError, match='no profile "nope"'):
        core.profile_settings("nope")
    with pytest.raises(UnknownProfileError, match='no profile "nope"'):
        core.change_profile_settings("nope", SettingsChange(ducking=False))
    with pytest.raises(BrokenProfileError, match=r'"broken-2000" cannot be read \(broken-2000\.json: must contain'):
        core.set_source_enabled("broken-2000", "messages", False)
    assert not (tmp_path / "settings" / "profiles").exists()


def test_core_rejects_voices_that_are_not_available(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    with pytest.raises(VoiceError, match=r'no voice "piper:missing"\. Available: piper:en_US'):
        change(core, voice="piper:missing")


def test_a_change_with_one_bad_setting_changes_nothing(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    events: list[Event] = []
    core.subscribe(events.append)

    with pytest.raises(VoiceError):
        change(core, ducking=False, voice="piper:missing")
    with pytest.raises(LanguageError):
        change(core, ducking=False, output_language="auto")

    assert core.status().ducking
    assert events == []
    assert not (tmp_path / "settings" / "profiles").exists()


def test_a_voice_is_previewed_in_its_language_without_touching_the_game_voice(tmp_path: Path) -> None:
    clients, previews = Clients(), Clients()
    core = make_core(tmp_path, clients, previews=previews)
    core._enter(playing(GTA2))

    core.preview_voice(ADAM.id)

    sample = "Tak ten głos czyta twoje gry."
    assert [(client.voice, client.said) for client in previews.started] == [(ADAM.id, [sample])]
    assert [client.voice for client in clients.started] == [LJSPEECH.id]
    with pytest.raises(VoiceError, match='no voice "piper:missing"'):
        core.preview_voice("piper:missing")


def test_output_language_switches_to_the_voice_last_used_for_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    change(core, voice=PAULINA.id)
    change(core, voice=LJSPEECH.id)

    view = change(core, output_language="pl")

    assert (view.output_language, view.voice) == ("pl", PAULINA.id)


def test_output_language_without_a_remembered_voice_takes_the_first_that_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    assert change(core, output_language="pl").voice == ADAM.id


def test_output_language_keeps_a_voice_that_already_speaks_it(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    change(core, voice=PAULINA.id)

    assert change(core, output_language="pl").voice == PAULINA.id


def test_output_language_without_any_voice_keeps_the_current_voice(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients(), voices=[LJSPEECH])

    view = change(core, output_language="pl")

    assert (view.output_language, view.voice) == ("pl", LJSPEECH.id)


def test_a_voice_chosen_with_an_output_language_wins_over_the_one_the_language_picks(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    view = change(core, output_language="pl", voice=PAULINA.id)

    assert (view.output_language, view.voice) == ("pl", PAULINA.id)


def test_languages_are_saved_and_checked(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    change(core, input_language="pl", output_language="pl")

    assert core.languages() == Languages(input="pl", output="pl")
    saved = saved_for(tmp_path, GTA2)
    assert (saved.input_language, saved.output_language) == ("pl", "pl")
    with pytest.raises(LanguageError, match='no language "auto"'):
        change(core, output_language="auto")
    with pytest.raises(LanguageError, match='no language "auto"'):
        change(core, input_language="auto")


def test_ducking_settings_are_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    view = change(core, ducking=False, duck_volume=0.5)

    assert (view.ducking, view.duck_volume) == (False, 0.5)
    assert (core.status().ducking, core.status().duck_volume) == (False, 0.5)
    saved = saved_for(tmp_path, GTA2)
    assert (saved.ducking, saved.duck_volume) == (False, 0.5)
    core.close()


def test_speech_settings_are_saved_and_used_for_the_next_line(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(GTA2))

    view = change(core, speech_rate=1.5, new_line=NewLine.CUT_OFF)
    core._narrator.say("hi")

    assert (view.speech_rate, view.new_line) == (1.5, "cut_off")
    saved = saved_for(tmp_path, GTA2)
    assert (saved.speech_rate, saved.new_line) == (1.5, NewLine.CUT_OFF)
    assert clients.started[0].how == [(1.5, NewLine.CUT_OFF)]
    core.close()


def test_subtitle_settings_are_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    view = change(core, subtitles=True, subtitle_size="large", subtitle_position="bottom")

    assert (view.subtitles, view.subtitle_size, view.subtitle_position) == (True, "large", "bottom")
    assert core.status().subtitles
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


BOTH_ON = {Output.TEXT: True, Output.SPEECH: True}


def test_stages_of_the_app_being_read_are_switched_per_output_and_stay_switched(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    view = core.set_stage_enabled(GTA2.id, "messages/1:suffix", Output.SPEECH, False)

    assert [stage.enabled for stage in view.sources[0].stages] == [BOTH_ON, {Output.TEXT: True, Output.SPEECH: False}]
    assert (view.sources[0].stages[0].type, view.sources[0].stages[0].summary) == ("suffix", "adds a suffix")
    assert core.status().sources == view.sources
    assert core.stage_switch("messages/1:suffix", Output.SPEECH) is False
    assert core.stage_switch("messages/1:suffix", Output.TEXT) is None
    core.set_stage_enabled(GTA2.id, "messages/1:suffix", Output.TEXT, True)
    assert saved_for(tmp_path, GTA2).stage_switches == {"messages/1:suffix": {Output.SPEECH: False, Output.TEXT: True}}


def test_the_user_can_switch_on_a_stage_its_profile_starts_off(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    speech_only = StageSettings("suffix", {}, text=False)
    core._enter(playing(replace(GTA2, sources=(replace(GTA2.sources[0], stages=(speech_only,)),))))

    assert core.status().sources[0].stages[0].enabled == {Output.TEXT: False, Output.SPEECH: True}
    view = core.set_stage_enabled(GTA2.id, "messages/0:suffix", Output.TEXT, True)
    assert view.sources[0].stages[0].enabled == BOTH_ON


def test_stages_of_a_profile_whose_app_does_not_run_are_switched_and_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    events: list[Event] = []
    core.subscribe(events.append)

    view = core.set_stage_enabled(GTA2.id, "messages/0:suffix", Output.TEXT, False)

    assert view.sources[0].stages[0].enabled == {Output.TEXT: False, Output.SPEECH: True}
    assert events == [view]
    assert saved_for(tmp_path, GTA2).stage_switches == {"messages/0:suffix": {Output.TEXT: False}}
    with pytest.raises(StageError, match='has no stage "messages/9:x"'):
        core.set_stage_enabled(GTA2.id, "messages/9:x", Output.TEXT, False)
    with pytest.raises(UnknownProfileError):
        core.set_stage_enabled("nope", "messages/0:suffix", Output.TEXT, False)


def test_sources_of_the_game_being_read_can_be_switched_off_and_stay_off(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))

    view = core.set_source_enabled(GTA2.id, "messages", False)

    assert (view.sources[0].type, view.sources[0].enabled) == ("fixed", False)
    assert not core.is_source_enabled("messages")
    assert saved_for(tmp_path, GTA2).disabled_sources == ("messages",)
    core.set_source_enabled(GTA2.id, "messages", True)
    assert saved_for(tmp_path, GTA2).disabled_sources == ()
    with pytest.raises(SourceError, match='has no source "signs"'):
        core.set_source_enabled(GTA2.id, "signs", False)


def test_sources_of_a_profile_whose_app_does_not_run_are_switched_and_saved(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())

    view = core.set_source_enabled(GTA2.id, "messages", False)

    assert (view.running, view.sources[0].enabled) == (False, False)
    assert saved_for(tmp_path, GTA2).disabled_sources == ("messages",)
    core._enter(playing(GTA2))
    assert not core.is_source_enabled("messages")


def test_each_game_keeps_its_own_settings(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(MAD_MAX))
    change(core, MAD_MAX, output_language="pl", speech_rate=1.5)
    core._leave()
    core._enter(playing(GTA2))
    change(core, speech_rate=0.8)
    core._leave()

    core._enter(playing(MAD_MAX))

    assert (core.status().output_language, core.status().speech_rate) == ("pl", 1.5)
    assert core.status().voice == ADAM.id
    assert saved_for(tmp_path, GTA2).speech_rate == 0.8


def test_a_game_played_for_the_first_time_starts_with_the_defaults(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    change(core, input_language="pl", voice=PAULINA.id)
    core.set_source_enabled(GTA2.id, "messages", False)
    core._leave()

    core._enter(playing(MAD_MAX))

    status = core.status()
    assert (status.input_language, status.voice) == ("en", DEFAULT_VOICE)
    assert core.is_source_enabled("messages")
    assert not (tmp_path / "settings" / "profiles" / f"{MAD_MAX.id}.json").exists()


def test_a_voice_is_loaded_only_while_a_game_is_read(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients)
    core._enter(playing(MAD_MAX))
    change(core, MAD_MAX, output_language="pl")
    core._leave()
    assert [client.voice for client in clients.started] == [DEFAULT_VOICE, "windows:Microsoft Adam"]

    core._enter(playing(MAD_MAX))

    assert [client.voice for client in clients.started][-1] == "windows:Microsoft Adam"
    assert len(clients.started) == 3
    assert all(client.closed for client in clients.started[:2])


def test_a_game_whose_voice_is_not_installed_speaks_with_another_for_its_language(tmp_path: Path) -> None:
    (tmp_path / "settings" / "profiles").mkdir(parents=True)
    (tmp_path / "settings" / "profiles" / f"{MAD_MAX.id}.json").write_text(
        '{"voice": "piper:pl_PL-gone-medium", "output_language": "pl"}', "utf-8"
    )
    clients = Clients()
    core = make_core(tmp_path, clients)

    core._enter(playing(MAD_MAX))

    assert [client.voice for client in clients.started] == ["windows:Microsoft Adam"]
    assert saved_for(tmp_path, MAD_MAX).voice == "piper:pl_PL-gone-medium"


def test_without_a_voice_for_the_output_language_nothing_is_spoken(tmp_path: Path) -> None:
    clients = Clients()
    core = make_core(tmp_path, clients, voices=[LJSPEECH])
    core._enter(playing(GTA2))

    view = change(core, output_language="pl")

    assert view.output_language == "pl"
    assert [client.closed for client in clients.started] == [True]
    change(core, output_language="en")
    assert len(clients.started) == 2 and not clients.started[1].closed


def test_a_voice_installed_while_a_game_is_read_is_used_right_away(tmp_path: Path) -> None:
    clients = Clients()
    installed = [LJSPEECH]
    core = make_core(tmp_path, clients, voices=installed)
    core._enter(playing(GTA2))
    change(core, output_language="pl")
    assert not clients.started[-1].said and clients.started[-1].closed
    events: list[Event] = []
    core.subscribe(events.append)

    installed.append(ADAM)
    core._downloaded(DownloadEvent("piper:pl_PL-adam", "installed"))

    assert clients.started[-1].voice == "windows:Microsoft Adam" and not clients.started[-1].closed
    assert events[0] == DownloadEvent("piper:pl_PL-adam", "installed")
    assert isinstance(events[-1], Status)


def test_no_voice_is_loaded_while_waiting_for_a_app(tmp_path: Path) -> None:
    clients = Clients()
    make_core(tmp_path, clients)

    assert clients.started == []


def test_the_defaults_apply_again_once_the_game_closes(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    change(core, input_language="pl")

    core._leave()

    assert core.status().input_language == "en"


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


POLISH_ONLY = app_with(SourceSettings("fixed", "messages", 0.25, {}, (StageSettings("polish", {}),))).profile


def test_the_status_says_why_a_stage_does_nothing_and_keeps_its_tick(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(POLISH_ONLY))

    stage = core.status().sources[0].stages[0]
    assert (stage.enabled, stage.inactive) == (BOTH_ON, "Only Polish")

    stage = change(core, POLISH_ONLY, output_language="pl").sources[0].stages[0]
    assert (stage.enabled, stage.inactive) == (BOTH_ON, None)
    assert core.status().sources[0].stages[0].inactive is None


def test_a_profile_s_stages_are_shown_for_its_own_languages(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients(), profiles=FixedProfiles(GTA2, POLISH_ONLY))
    core._enter(playing(GTA2))

    assert core.profile_settings(POLISH_ONLY.id).sources[0].stages[0].inactive == "Only Polish"
    stage = change(core, POLISH_ONLY, output_language="pl").sources[0].stages[0]

    assert stage.inactive is None
    assert core.status().output_language == "en"


def core_playing(tmp_path: Path, is_running: Callable[[int], bool], exit_grace_seconds: float) -> Core:
    core = Core(
        profiles=FixedProfiles(),
        settings_dir=tmp_path,
        narrator_factory=lambda voice, on_speaking: Narrator(voice, Clients().start, on_speaking),
        list_voices=lambda: [ADAM],
        is_running=is_running,
        stages=STAGES,
        open_app_volume=no_sound,
        duck_records=DuckRecords(tmp_path / "lowered-apps.json"),
        exit_grace_seconds=exit_grace_seconds,
        download_sources={},
    )
    core._app = AppInfo("App", 42, "app")
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


def test_changes_made_at_the_same_time_are_all_kept(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._enter(playing(GTA2))
    rounds = 300
    start = threading.Barrier(2)

    def change_ducking() -> None:
        start.wait()
        for step in range(rounds):
            change(core, duck_volume=step / rounds)

    def change_speech() -> None:
        start.wait()
        for step in range(rounds):
            change(core, speech_rate=1.0 + step / rounds)

    threads = [threading.Thread(target=change_ducking), threading.Thread(target=change_speech)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    last_volume, last_rate = (rounds - 1) / rounds, 1.0 + (rounds - 1) / rounds
    status = core.status()
    assert (status.duck_volume, status.speech_rate) == (last_volume, last_rate)
    saved = saved_for(tmp_path, GTA2)
    assert (saved.duck_volume, saved.speech_rate) == (last_volume, last_rate)


def test_an_unsupported_build_is_reported_until_it_exits_and_not_read(tmp_path: Path) -> None:
    core = core_playing(tmp_path, lambda pid: False, exit_grace_seconds=0)
    core._app = None
    events: list[Event] = []
    core.subscribe(events.append)
    unsupported = RunningApp(GTA2, ProcessInfo(7, "gta2.exe"), build="abc", supported=False)

    core._wait_while_unsupported(unsupported, threading.Event())

    statuses = [event for event in events if isinstance(event, Status)]
    assert [status.unsupported for status in statuses] == [UnsupportedApp("Grand Theft Auto 2", "abc"), None]
    assert all(status.app is None for status in statuses)


def test_a_disabled_profile_is_saved_stops_being_read_and_shows_its_state(tmp_path: Path) -> None:
    core = make_core(tmp_path, Clients())
    core._is_running = lambda pid: True
    core._enter(playing(GTA2))
    watching = core._watching(playing(GTA2))
    events: list[Event] = []
    core.subscribe(events.append)

    assert [view.state for view in core.profiles()] == [ProfileState.READING]
    assert watching(42)
    status = core.set_profile_enabled(GTA2.id, False)

    assert events == [status]
    assert not watching(42)
    assert [view.state for view in core.profiles()] == [ProfileState.DISABLED]
    assert load_shared(tmp_path).disabled_profiles == (GTA2.id,)
    core.set_profile_enabled(GTA2.id, True)
    assert load_shared(tmp_path).disabled_profiles == ()
    with pytest.raises(UnknownProfileError, match='no profile "nope"'):
        core.set_profile_enabled("nope", False)


def test_profiles_imported_copied_or_removed_count_at_once(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    game = {"version": 1, "app": {"title": "Game", "year": 2000}, "match": {"executables": [{"name": "game.exe"}]}}
    (bundled / "game-2000.json").write_text(json.dumps(game), "utf-8")
    store = ProfileStore(tmp_path / "user", bundled, PluginSchemas(sources={}, stages={}))
    core = make_core(tmp_path, Clients(), profiles=store)
    events: list[Event] = []
    core.subscribe(events.append)

    core.import_profile("mine-2001", game | {"app": {"title": "Mine", "year": 2001}}, replace=False)
    copy = core.copy_profile("game-2000")

    assert copy == tmp_path / "user" / "game-2000.json"
    assert [(view.choice.entry.id, view.choice.entry.origin, view.state) for view in core.profiles()] == [
        ("game-2000", Origin.OVERRIDE, ProfileState.CLASH),
        ("mine-2001", Origin.CUSTOM, ProfileState.CLASH),
    ]
    core.remove_profile("mine-2001")
    assert [view.state for view in core.profiles()] == [ProfileState.NOT_RUNNING]
    assert len([event for event in events if isinstance(event, Status)]) == 3
    with pytest.raises(UnknownProfileError):
        core.remove_profile("mine-2001")


def test_without_a_game_the_status_shows_the_voice_a_new_game_would_get(tmp_path: Path) -> None:
    # The default voice is not installed; a new game would speak English with the installed one.
    alan = VoiceInfo("piper:en_GB-alan-low", "piper", "en_GB-alan-low", "en-GB", "Piper")
    core = make_core(tmp_path, Clients(), voices=[alan, ADAM])

    assert core.status().voice == alan.id

    core._enter(playing(GTA2))
    core._leave()

    assert core.status().voice == alan.id
