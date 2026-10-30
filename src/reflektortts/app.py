"""The core: watches for profiled games, reads them aloud, and answers the local API."""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import platformdirs
import psutil

from reflektortts.api.server import ApiServer
from reflektortts.bus import EventBus, Listener
from reflektortts.events import ErrorEvent, GameInfo, Status
from reflektortts.games.detector import RunningGame, find_running_games
from reflektortts.overlay import inject_overlay
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, source_plugins, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Route, Runner, log_error
from reflektortts.profiles.loader import load_profiles
from reflektortts.profiles.model import Profile
from reflektortts.settings import load_settings, save_settings
from reflektortts.sinks.bus import BusSink
from reflektortts.sinks.tts import TtsSink
from reflektortts.tts.engine import VoiceError, VoiceInfo, available_voices
from reflektortts.tts.narrator import Narrator

logger = logging.getLogger(__name__)

GAME_CHECK_SECONDS = 2.0


def default_profiles_dir() -> Path:
    return platformdirs.user_data_path("reflektortts", appauthor=False) / "profiles"


def build_routes(
    game: RunningGame,
    sources: Mapping[str, SourcePlugin],
    stages: Mapping[str, StagePlugin],
    on_error: Callable[[ErrorEvent], None],
) -> list[Route]:
    """Creates the game's sources and their stages; a source that cannot start is reported and skipped."""
    routes = []
    for settings in game.profile.sources:
        try:
            source = sources[settings.type].create(settings, game)
        except Exception as error:
            on_error(ErrorEvent("source.error", settings.name, str(error)))
            continue
        routes.append(Route(source, [stages[stage.type].create(stage.settings) for stage in settings.stages]))
    return routes


def read_game(
    game: RunningGame,
    routes: Sequence[Route],
    sinks: Sequence[Sink],
    stop: threading.Event,
    on_error: Callable[[ErrorEvent], None] = log_error,
    is_running: Callable[[int], bool] = psutil.pid_exists,
    check_seconds: float = GAME_CHECK_SECONDS,
) -> None:
    """Runs the pipeline until the game exits or stop is set, then closes the sources."""
    runner_stop = threading.Event()
    worker = threading.Thread(target=Runner(routes, sinks, on_error).run, args=(runner_stop,), name="runner")
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
        narrator_factory: Callable[[str], Narrator] = Narrator,
        list_voices: Callable[[], list[VoiceInfo]] = available_voices,
        is_running: Callable[[int], bool] = psutil.pid_exists,
    ) -> None:
        self._profiles = profiles
        self._is_running = is_running
        self._settings_file = settings_file
        self._settings = load_settings(settings_file)
        self._overlay_dirs = overlay_dirs
        self._list_voices = list_voices
        self._narrator = narrator_factory(self._settings.voice)
        self._bus = EventBus()
        self._game: GameInfo | None = None

    def status(self) -> Status:
        return Status(game=self._game, voice=self._narrator.voice, paused=self._narrator.paused)

    def voices(self) -> list[VoiceInfo]:
        return self._list_voices()

    def set_voice(self, voice: str) -> Status:
        available = [info.id for info in self.voices()]
        if voice not in available:
            raise VoiceError(f'There is no voice "{voice}". Available: {", ".join(available) or "none"}.')
        self._narrator.use_voice(voice)
        self._settings = replace(self._settings, voice=voice)
        save_settings(self._settings, self._settings_file)
        return self._publish_status()

    def set_paused(self, paused: bool) -> Status:
        if paused:
            self._narrator.pause()
        else:
            self._narrator.resume()
        return self._publish_status()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self._bus.subscribe(listener)

    def run(self, stop: threading.Event) -> None:
        """Reads every profiled game that starts, one at a time, until stop is set."""
        sources, stages = source_plugins(), stage_plugins()
        sinks: list[Sink] = [TtsSink(self._narrator), BusSink(self._bus)]
        logger.info("Watching for %s", ", ".join(profile.game.title for profile in self._profiles))
        while not stop.is_set():
            games = find_running_games(self._profiles)
            if not games:
                stop.wait(GAME_CHECK_SECONDS)
                continue
            game = games[0]
            self._game = GameInfo(title=game.profile.game.title, pid=game.process.pid)
            self._publish_status()
            if self._overlay_dirs:
                inject_overlay(game.process.pid, self._overlay_dirs)
            routes = build_routes(game, sources, stages, self._report)
            if routes:
                logger.info("Reading %s aloud", game.profile.game.title)
            else:
                logger.error("%s is running, but none of its sources could start.", game.profile.game.title)
            read_game(game, routes, sinks, stop, self._report, self._is_running)
            logger.info("%s closed", game.profile.game.title)
            self._game = None
            self._publish_status()

    def close(self) -> None:
        self._narrator.close()

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
