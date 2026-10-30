"""The core: watches for profiled games, reads them aloud, and answers the local API."""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import platformdirs
import psutil

from reflektortts.api.server import ApiServer, SourceError, StageError
from reflektortts.bus import EventBus, Listener
from reflektortts.ducking.ducker import Ducker
from reflektortts.ducking.records import DuckRecords, records_path
from reflektortts.ducking.volume import DuckingUnavailableError, OpenAppVolume, system_app_volume
from reflektortts.events import ErrorEvent, GameInfo, SourceStages, StageState, Status
from reflektortts.games.detector import RunningGame, find_running_games
from reflektortts.languages import (
    AUTO,
    DEFAULT_SPEECH_LANGUAGE,
    Languages,
    check_game_language,
    check_speech_language,
    primary_language,
)
from reflektortts.overlay import inject_overlay
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, source_plugins, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Route, Runner, log_error
from reflektortts.profiles.loader import load_profiles
from reflektortts.profiles.model import Profile
from reflektortts.settings import Settings, load_settings, save_settings
from reflektortts.sinks.bus import BusSink
from reflektortts.sinks.tts.narrator import Narrator
from reflektortts.sinks.tts.sink import TtsSink
from reflektortts.tts.engine import VoiceError, VoiceInfo, available_voices

logger = logging.getLogger(__name__)

GAME_CHECK_SECONDS = 2.0


def default_profiles_dir() -> Path:
    return platformdirs.user_data_path("reflektortts", appauthor=False) / "profiles"


def start_narrator(voice: str, on_speaking: Callable[[bool], None]) -> Narrator:
    return Narrator(voice, on_speaking=on_speaking)


def app_volume() -> OpenAppVolume:
    """This system's per-app volume, or one that finds no sound, so nothing is lowered."""
    try:
        return system_app_volume()
    except DuckingUnavailableError as error:
        logger.info("%s", error)
        return lambda pid: None


def stage_key(source: str, position: int, stage_type: str) -> str:
    """Identifies a stage within its profile, e.g. "messages/2:normalize"."""
    return f"{source}/{position}:{stage_type}"


def _enabled_check(source: str, types: Sequence[str], is_enabled: Callable[[str], bool]) -> Callable[[int], bool]:
    return lambda position: is_enabled(stage_key(source, position, types[position]))


def _source_check(source: str, is_source_enabled: Callable[[str], bool]) -> Callable[[], bool]:
    return lambda: is_source_enabled(source)


def _switched(disabled: dict[str, list[str]], profile_id: str, key: str, enabled: bool) -> dict[str, list[str]]:
    """Switched-off keys by profile ID, with key switched on or off for one profile."""
    keys = set(disabled.get(profile_id, []))
    keys = keys - {key} if enabled else keys | {key}
    stored = disabled | {profile_id: sorted(keys)}
    return {profile: keys for profile, keys in stored.items() if keys}


def build_routes(
    game: RunningGame,
    sources: Mapping[str, SourcePlugin],
    stages: Mapping[str, StagePlugin],
    on_error: Callable[[ErrorEvent], None],
    is_enabled: Callable[[str], bool] = lambda key: True,
    is_source_enabled: Callable[[str], bool] = lambda name: True,
) -> list[Route]:
    """Creates the game's sources and their stages; a source that cannot start is reported and skipped.

    is_enabled tells, by stage key, whether the player has the stage switched on; is_source_enabled
    tells the same for a source, by name.
    """
    routes = []
    for settings in game.profile.sources:
        try:
            source = sources[settings.type].create(settings, game)
        except Exception as error:
            on_error(ErrorEvent("source.error", settings.name, str(error)))
            continue
        types = [stage.type for stage in settings.stages]
        routes.append(
            Route(
                source,
                [stages[stage.type].create(stage.settings) for stage in settings.stages],
                _enabled_check(settings.name, types, is_enabled),
                _source_check(settings.name, is_source_enabled),
            )
        )
    return routes


def read_game(
    game: RunningGame,
    routes: Sequence[Route],
    sinks: Sequence[Sink],
    stop: threading.Event,
    on_error: Callable[[ErrorEvent], None] = log_error,
    is_running: Callable[[int], bool] = psutil.pid_exists,
    check_seconds: float = GAME_CHECK_SECONDS,
    languages: Callable[[], Languages] = lambda: Languages(game=AUTO, speech=DEFAULT_SPEECH_LANGUAGE),
) -> None:
    """Runs the pipeline until the game exits or stop is set, then closes the sources."""
    runner_stop = threading.Event()
    runner = Runner(routes, sinks, on_error, languages=languages)
    worker = threading.Thread(target=runner.run, args=(runner_stop,), name="runner")
    worker.start()
    try:
        while is_running(game.process.pid) and not stop.wait(check_seconds):
            pass
    finally:
        runner_stop.set()
        worker.join()
        for route in routes:
            route.source.close()


class Core:
    """Owns the narrator, the settings and the event bus; the API controls it through these methods."""

    def __init__(
        self,
        profiles: Sequence[Profile],
        settings_file: Path,
        overlay_dirs: Sequence[Path] = (),
        narrator_factory: Callable[[str, Callable[[bool], None]], Narrator] = start_narrator,
        list_voices: Callable[[], list[VoiceInfo]] = available_voices,
        is_running: Callable[[int], bool] = psutil.pid_exists,
        stages: Mapping[str, StagePlugin] | None = None,
        open_app_volume: Callable[[], OpenAppVolume] = app_volume,
        duck_records: DuckRecords | None = None,
    ) -> None:
        self._profiles = profiles
        self._is_running = is_running
        self._settings_file = settings_file
        self._settings = load_settings(settings_file)
        self._overlay_dirs = overlay_dirs
        self._list_voices = list_voices
        self._stages = stage_plugins() if stages is None else stages
        self._ducker = Ducker(
            open_app_volume(),
            DuckRecords(records_path()) if duck_records is None else duck_records,
            self._settings.ducking,
            self._settings.duck_volume,
        )
        self._narrator = narrator_factory(self._settings.voice, self._ducker.speaking)
        self._bus = EventBus()
        self._game: GameInfo | None = None
        self._profile: Profile | None = None

    def status(self) -> Status:
        return Status(
            game=self._game,
            voice=self._narrator.voice,
            game_language=self._settings.game_language,
            speech_language=self._settings.speech_language,
            paused=self._narrator.paused,
            ducking=self._settings.ducking,
            duck_volume=self._settings.duck_volume,
            sources=self._source_stages(),
        )

    def languages(self) -> Languages:
        return Languages(game=self._settings.game_language, speech=self._settings.speech_language)

    def set_game_language(self, language: str) -> Status:
        check_game_language(language)
        self._save(replace(self._settings, game_language=language))
        return self._publish_status()

    def set_speech_language(self, language: str) -> Status:
        """Also switches to a voice for the language, unless the current one speaks it."""
        check_speech_language(language)
        voice = self._voice_for(language)
        if voice is not None:
            self._narrator.use_voice(voice)
        self._save(replace(self._settings, speech_language=language, voice=self._narrator.voice))
        return self._publish_status()

    def voices(self) -> list[VoiceInfo]:
        return self._list_voices()

    def set_voice(self, voice: str) -> Status:
        """Switches the voice and remembers it as the last one used for its language."""
        voices = {info.id: info for info in self.voices()}
        if voice not in voices:
            raise VoiceError(f'There is no voice "{voice}". Available: {", ".join(voices) or "none"}.')
        self._narrator.use_voice(voice)
        remembered = self._settings.voices_by_language | {primary_language(voices[voice].language): voice}
        self._save(replace(self._settings, voice=voice, voices_by_language=remembered))
        return self._publish_status()

    def set_ducking(self, enabled: bool, volume: float) -> Status:
        """Whether, and how far, the game's sound is lowered while lines are spoken."""
        self._ducker.configure(enabled, volume)
        self._save(replace(self._settings, ducking=enabled, duck_volume=volume))
        return self._publish_status()

    def set_paused(self, paused: bool) -> Status:
        if paused:
            self._narrator.pause()
        else:
            self._narrator.resume()
        return self._publish_status()

    def stop_line(self) -> Status:
        self._narrator.stop_line()
        return self.status()

    def is_source_enabled(self, name: str) -> bool:
        profile = self._profile
        return profile is None or name not in self._settings.disabled_sources.get(profile.id, [])

    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        """Switches a source of the game being read on or off; the choice is saved for that game."""
        profile = self._profile
        if profile is None:
            raise SourceError("No game is being read.")
        names = [source.name for source in profile.sources]
        if name not in names:
            raise SourceError(f'{profile.game.title} has no source "{name}". Its sources: {", ".join(names)}.')
        disabled = _switched(self._settings.disabled_sources, profile.id, name, enabled)
        self._save(replace(self._settings, disabled_sources=disabled))
        return self._publish_status()

    def is_stage_enabled(self, key: str) -> bool:
        profile = self._profile
        return profile is None or key not in self._settings.disabled_stages.get(profile.id, [])

    def set_stage_enabled(self, key: str, enabled: bool) -> Status:
        """Switches a stage of the game being read on or off; the choice is saved for that game."""
        profile = self._profile
        if profile is None:
            raise StageError("No game is being read.")
        keys = [stage.key for source in self._source_stages() for stage in source.stages]
        if key not in keys:
            raise StageError(f'{profile.game.title} has no stage "{key}". Its stages: {", ".join(keys)}.')
        disabled = _switched(self._settings.disabled_stages, profile.id, key, enabled)
        self._save(replace(self._settings, disabled_stages=disabled))
        return self._publish_status()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self._bus.subscribe(listener)

    def run(self, stop: threading.Event) -> None:
        """Reads every profiled game that starts, one at a time, until stop is set."""
        sources = source_plugins()
        sinks: list[Sink] = [TtsSink(self._narrator), BusSink(self._bus)]
        logger.info("Watching for %s", ", ".join(profile.game.title for profile in self._profiles))
        while not stop.is_set():
            games = find_running_games(self._profiles)
            if not games:
                stop.wait(GAME_CHECK_SECONDS)
                continue
            game = games[0]
            self._game = GameInfo(title=game.profile.game.title, pid=game.process.pid)
            self._profile = game.profile
            self._publish_status()
            self._ducker.watch(game.process)
            if self._overlay_dirs:
                inject_overlay(game.process.pid, self._overlay_dirs)
            routes = build_routes(
                game, sources, self._stages, self._report, self.is_stage_enabled, self.is_source_enabled
            )
            if routes:
                logger.info("Reading %s aloud", game.profile.game.title)
            else:
                logger.error("%s is running, but none of its sources could start.", game.profile.game.title)
            read_game(game, routes, sinks, stop, self._report, self._is_running, languages=self.languages)
            logger.info("%s closed", game.profile.game.title)
            self._ducker.watch(None)
            self._game = None
            self._profile = None
            self._publish_status()

    def close(self) -> None:
        self._narrator.close()
        self._ducker.close()

    def _source_stages(self) -> tuple[SourceStages, ...]:
        profile = self._profile
        if profile is None:
            return ()
        return tuple(
            SourceStages(
                source=source.name,
                type=source.type,
                enabled=self.is_source_enabled(source.name),
                stages=tuple(
                    self._stage_state(stage_key(source.name, position, stage.type), stage.type)
                    for position, stage in enumerate(source.stages)
                ),
            )
            for source in profile.sources
        )

    def _stage_state(self, key: str, stage_type: str) -> StageState:
        plugin = self._stages.get(stage_type)
        return StageState(
            key=key,
            type=stage_type,
            summary=plugin.summary if plugin is not None else "",
            warning=plugin.warning_when_disabled if plugin is not None else None,
            enabled=self.is_stage_enabled(key),
        )

    def _voice_for(self, language: str) -> str | None:
        """The voice to switch to for a speech language, or None to keep the current one.

        The current voice stays if it speaks the language; otherwise the one last used for
        the language, else the first that speaks it. With no voice for it, nothing changes.
        """
        voices = self.voices()
        current = next((voice for voice in voices if voice.id == self._narrator.voice), None)
        if current is not None and primary_language(current.language) == language:
            return None
        matching = [voice.id for voice in voices if primary_language(voice.language) == language]
        remembered = self._settings.voices_by_language.get(language)
        if remembered in matching:
            return remembered
        return matching[0] if matching else None

    def _save(self, settings: Settings) -> None:
        self._settings = settings
        save_settings(settings, self._settings_file)

    def _report(self, error: ErrorEvent) -> None:
        # A source usually fails a moment before the game's exit is noticed; that is not an error.
        game = self._game
        if error.kind == "source.error" and game is not None and not self._is_running(game.pid):
            logger.debug("Ignoring %s from %s: the game has exited", error.kind, error.origin)
            return
        log_error(error)
        self._bus.publish(error)

    def _publish_status(self) -> Status:
        status = self.status()
        self._bus.publish(status)
        return status


def run(profiles_dir: Path, settings_file: Path, overlay_dirs: Sequence[Path], stop: threading.Event) -> None:
    """Starts the core and its API, and runs until stop is set or the process is interrupted."""
    profiles, errors = load_profiles(profiles_dir) if profiles_dir.is_dir() else ([], [])
    for error in errors:
        logger.error("Skipping a profile: %s", error)
    if not profiles:
        logger.error("No game profiles in %s. Copy a profile there or pass --profiles.", profiles_dir)
        return

    core = Core(profiles, settings_file, overlay_dirs)
    server = ApiServer(core)
    try:
        server.start()
        core.run(stop)
    finally:
        server.stop()
        core.close()
