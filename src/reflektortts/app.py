"""The core's main loop: waits for a profiled game and reads it aloud until it exits."""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import platformdirs
import psutil

from reflektortts.events import ErrorEvent
from reflektortts.games.detector import RunningGame, find_running_games
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, source_plugins, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Route, Runner, log_error
from reflektortts.profiles.loader import load_profiles
from reflektortts.sinks.tts import TtsSink
from reflektortts.tts.client import TtsClient

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


def run(profiles_dir: Path, voice: str, stop: threading.Event) -> None:
    """Reads every profiled game that starts, one at a time, until stop is set."""
    profiles, errors = load_profiles(profiles_dir) if profiles_dir.is_dir() else ([], [])
    for error in errors:
        logger.error("Skipping a profile: %s", error)
    if not profiles:
        logger.error("No game profiles in %s. Copy a profile there or pass --profiles.", profiles_dir)
        return
    logger.info("Watching for %s", ", ".join(profile.game.title for profile in profiles))

    sources, stages = source_plugins(), stage_plugins()
    with TtsClient(voice) as tts:
        sinks = [TtsSink(tts)]
        while not stop.is_set():
            games = find_running_games(profiles)
            if not games:
                stop.wait(GAME_CHECK_SECONDS)
                continue
            game = games[0]
            routes = build_routes(game, sources, stages, log_error)
            if not routes:
                logger.error("%s is running, but none of its sources could start.", game.profile.game.title)
            else:
                logger.info("Reading %s aloud", game.profile.game.title)
            read_game(game, routes, sinks, stop)
            logger.info("%s closed", game.profile.game.title)
