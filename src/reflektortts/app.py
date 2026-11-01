"""The core: watches for profiled games, reads them aloud, and answers the local API."""

import functools
import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Concatenate

import psutil

from reflektortts.api.server import ApiServer, SourceError, StageError
from reflektortts.bus import EventBus, Listener
from reflektortts.downloads.manager import Downloads, Listing
from reflektortts.downloads.source import DownloadSource, download_plugins
from reflektortts.ducking.ducker import Ducker
from reflektortts.ducking.records import DuckRecords, records_path
from reflektortts.ducking.volume import DuckingUnavailableError, OpenAppVolume, system_app_volume
from reflektortts.events import DownloadEvent, ErrorEvent, GameInfo, PreviewEvent, SourceStages, StageState, Status
from reflektortts.games.detector import RunningGame, find_running_games
from reflektortts.languages import (
    DEFAULT_GAME_LANGUAGE,
    DEFAULT_OUTPUT_LANGUAGE,
    SAMPLES,
    Languages,
    check_language,
    primary_language,
)
from reflektortts.overlay import inject_overlay
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, inactive_reason, source_plugins, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Route, Runner, log_error
from reflektortts.profiles.loader import load_profiles
from reflektortts.profiles.model import Profile
from reflektortts.settings import GameSettings, load_game, load_shared, save_game, save_shared
from reflektortts.sinks.bus import BusSink
from reflektortts.sinks.subtitles import Subtitles
from reflektortts.sinks.tts.narrator import Narrator
from reflektortts.sinks.tts.preview import VoicePreview
from reflektortts.sinks.tts.sink import TtsSink
from reflektortts.tts.engine import VoiceError, VoiceInfo, available_voices, find_voice
from reflektortts.user_dirs import cache_dir, data_dir

logger = logging.getLogger(__name__)

GAME_CHECK_SECONDS = 2.0
EXIT_GRACE_SECONDS = 2.0
"""How long a source error waits for the game to exit before it is reported: while a game exits,
its memory is torn down before Windows counts the process as gone, so sources fail first."""
EXIT_CHECK_SECONDS = 0.1


def default_profiles_dir() -> Path:
    return data_dir() / "profiles"


def load_download_sources() -> dict[str, DownloadSource]:
    """Every download source plugin, each with a cache folder of its own; a failing one is logged."""
    sources = {}
    for name, plugin in download_plugins().items():
        try:
            sources[name] = plugin.create(cache_dir() / "downloads" / name)
        except Exception:
            logger.exception("Download source %s is not available", name)
    return sources


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
    """Identifies a stage within its profile, e.g. "subtitles/3:normalize"."""
    return f"{source}/{position}:{stage_type}"


def _enabled_check(
    source: str,
    types: Sequence[str],
    plugins: Mapping[str, StagePlugin],
    is_enabled: Callable[[str], bool],
    languages: Callable[[], Languages],
) -> Callable[[int], bool]:
    """Whether the stage at a position runs: the player has it switched on, and it works with the
    player's languages."""
    return lambda position: (
        is_enabled(stage_key(source, position, types[position]))
        and inactive_reason(plugins[types[position]], languages()) is None
    )


def _source_check(source: str, is_source_enabled: Callable[[str], bool]) -> Callable[[], bool]:
    return lambda: is_source_enabled(source)


def _switched(disabled: tuple[str, ...], key: str, enabled: bool) -> tuple[str, ...]:
    """Switched-off keys, with key switched on or off."""
    return tuple(sorted(set(disabled) - {key} if enabled else set(disabled) | {key}))


def build_routes(
    game: RunningGame,
    sources: Mapping[str, SourcePlugin],
    stages: Mapping[str, StagePlugin],
    on_error: Callable[[ErrorEvent], None],
    is_enabled: Callable[[str], bool] = lambda key: True,
    is_source_enabled: Callable[[str], bool] = lambda name: True,
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_GAME_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
) -> list[Route]:
    """Creates the game's sources and their stages; a source that cannot start, or one of whose
    stages cannot, is reported and skipped.

    is_enabled tells, by stage key, whether the player has the stage switched on; is_source_enabled
    tells the same for a source, by name. A stage that does nothing with the player's languages is
    skipped too.
    """
    routes = []
    for settings in game.profile.sources:
        try:
            source = sources[settings.type].create(settings, game)
        except Exception as error:
            on_error(ErrorEvent("source.error", settings.name, str(error)))
            continue
        try:
            created = [stages[stage.type].create(stage.settings) for stage in settings.stages]
        except Exception as error:
            source.close()
            on_error(ErrorEvent("source.error", settings.name, f"A text processing stage cannot start ({error})."))
            continue
        types = [stage.type for stage in settings.stages]
        routes.append(
            Route(
                source,
                created,
                _enabled_check(settings.name, types, stages, is_enabled, languages),
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
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_GAME_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
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


def _serialized[**P, R](method: Callable[Concatenate["Core", P], R]) -> Callable[Concatenate["Core", P], R]:
    """Runs a Core method holding the core's lock, so changes from the API, the core thread and
    downloads are made one at a time, each in full, and a status is never half old, half new."""

    @functools.wraps(method)
    def serialized(core: "Core", /, *args: P.args, **kwargs: P.kwargs) -> R:
        with core._lock:
            return method(core, *args, **kwargs)

    return serialized


class Core:
    """Owns the narrator, the settings and the event bus; the API controls it through these methods.

    Settings belong to the game being read and are saved for it; a game starts with the defaults
    until the player changes something in it. While no game is read, the defaults apply and
    changes are not saved.
    """

    def __init__(
        self,
        profiles: Sequence[Profile],
        settings_dir: Path,
        overlay_dirs: Sequence[Path] = (),
        narrator_factory: Callable[[str, Callable[[bool], None]], Narrator] = start_narrator,
        list_voices: Callable[[], list[VoiceInfo]] = available_voices,
        is_running: Callable[[int], bool] = psutil.pid_exists,
        stages: Mapping[str, StagePlugin] | None = None,
        open_app_volume: Callable[[], OpenAppVolume] = app_volume,
        duck_records: DuckRecords | None = None,
        exit_grace_seconds: float = EXIT_GRACE_SECONDS,
        download_sources: Mapping[str, DownloadSource] | None = None,
        preview_factory: Callable[[Callable[[PreviewEvent], None]], VoicePreview] = VoicePreview,
    ) -> None:
        self._lock = threading.RLock()
        """Held by every change; reentrant, since changes call each other and status()."""
        self._profiles = profiles
        self._is_running = is_running
        self._exit_grace_seconds = exit_grace_seconds
        self._settings_dir = settings_dir
        self._shared = load_shared(settings_dir)
        self._settings = GameSettings()
        self._overlay_dirs = overlay_dirs
        self._list_voices = list_voices
        self._stages = stage_plugins() if stages is None else stages
        self._ducker = Ducker(
            open_app_volume(),
            DuckRecords(records_path()) if duck_records is None else duck_records,
            self._settings.ducking,
            self._settings.duck_volume,
        )
        self._bus = EventBus()
        self._subtitles = Subtitles(self._bus.publish, self._settings.subtitles)
        self._narrator = narrator_factory(self._settings.voice, self._speaking)
        self._narrator.configure(self._settings.speech_rate, self._settings.cut_off_lines)
        self._game: GameInfo | None = None
        self._profile: Profile | None = None
        sources = load_download_sources() if download_sources is None else download_sources
        self._downloads = Downloads(sources, self._downloaded)
        self._preview = preview_factory(self._bus.publish)

    @_serialized
    def status(self) -> Status:
        return Status(
            game=self._game,
            voice=self._narrator.voice,
            game_language=self._settings.game_language,
            output_language=self._settings.output_language,
            paused=self._narrator.paused,
            ducking=self._settings.ducking,
            duck_volume=self._settings.duck_volume,
            speech_rate=self._settings.speech_rate,
            cut_off_lines=self._settings.cut_off_lines,
            subtitles=self._settings.subtitles,
            subtitle_size=self._settings.subtitle_size,
            subtitle_position=self._settings.subtitle_position,
            sources=self._source_stages(),
        )

    def languages(self) -> Languages:
        return Languages(game=self._settings.game_language, output=self._settings.output_language)

    @_serialized
    def set_game_language(self, language: str) -> Status:
        check_language(language)
        self._change(game_language=language)
        return self._publish_status()

    @_serialized
    def set_output_language(self, language: str) -> Status:
        """Also switches to a voice for the language, unless the current one speaks it. Any
        language can be chosen: without a voice for it, lines are translated and shown, not spoken."""
        check_language(language)
        voice = self._voice_for(language, self._settings.voice)
        self._change(output_language=language, voice=voice or self._settings.voice)
        self._speak()
        return self._publish_status()

    def voices(self) -> list[VoiceInfo]:
        return self._list_voices()

    @_serialized
    def set_voice(self, voice: str) -> Status:
        """Switches the voice and remembers it as the last one used for its language."""
        info = find_voice(voice, self.voices())
        remembered = self._shared.voices_by_language | {primary_language(info.language): voice}
        self._shared = replace(self._shared, voices_by_language=remembered)
        save_shared(self._shared, self._settings_dir)
        self._change(voice=voice)
        self._speak()
        return self._publish_status()

    def preview_voice(self, voice: str) -> None:
        """Speaks a sample sentence in the voice's language, also while a game is read."""
        language = primary_language(find_voice(voice, self.voices()).language)
        if language not in SAMPLES:
            raise VoiceError(f'"{voice}" speaks {language}, a language ReflektorTTS does not support.')
        self._preview.play(voice, SAMPLES[language])

    @_serialized
    def set_ducking(self, enabled: bool, volume: float) -> Status:
        """Whether, and how far, the game's sound is lowered while lines are spoken."""
        self._ducker.configure(enabled, volume)
        self._change(ducking=enabled, duck_volume=volume)
        return self._publish_status()

    @_serialized
    def set_speech(self, rate: float, cut_off: bool) -> Status:
        """How fast lines are spoken, and whether a new line cuts off the one being spoken."""
        self._narrator.configure(rate, cut_off)
        self._change(speech_rate=rate, cut_off_lines=cut_off)
        return self._publish_status()

    @_serialized
    def set_subtitles(self, enabled: bool, size: str, position: str) -> Status:
        """Whether lines are shown as subtitles over the game, how large and where."""
        self._subtitles.configure(enabled)
        self._change(subtitles=enabled, subtitle_size=size, subtitle_position=position)
        return self._publish_status()

    @_serialized
    def set_paused(self, paused: bool) -> Status:
        if paused:
            self._narrator.pause()
        else:
            self._narrator.resume()
        return self._publish_status()

    @_serialized
    def stop_line(self) -> Status:
        self._narrator.stop_line()
        return self.status()

    def is_source_enabled(self, name: str) -> bool:
        return name not in self._settings.disabled_sources

    @_serialized
    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        """Switches a source of the game being read on or off; the choice is saved for that game."""
        profile = self._profile
        if profile is None:
            raise SourceError("No game is being read.")
        names = [source.name for source in profile.sources]
        if name not in names:
            raise SourceError(f'{profile.game.title} has no source "{name}". Its sources: {", ".join(names)}.')
        self._change(disabled_sources=_switched(self._settings.disabled_sources, name, enabled))
        return self._publish_status()

    def is_stage_enabled(self, key: str) -> bool:
        return key not in self._settings.disabled_stages

    @_serialized
    def set_stage_enabled(self, key: str, enabled: bool) -> Status:
        """Switches a stage of the game being read on or off; the choice is saved for that game."""
        profile = self._profile
        if profile is None:
            raise StageError("No game is being read.")
        keys = [stage.key for source in self._source_stages() for stage in source.stages]
        if key not in keys:
            raise StageError(f'{profile.game.title} has no stage "{key}". Its stages: {", ".join(keys)}.')
        self._change(disabled_stages=_switched(self._settings.disabled_stages, key, enabled))
        return self._publish_status()

    def downloads(self, refresh: bool) -> Listing:
        """What can be downloaded, with what is installed or downloading; refresh fetches the lists."""
        return self._downloads.listing(refresh)

    def start_download(self, entry_id: str) -> None:
        """Starts downloading an entry; progress comes as DownloadEvents. Raises DownloadError."""
        self._downloads.start(entry_id)

    def remove_download(self, entry_id: str) -> None:
        """Removes an installed entry. Raises DownloadError."""
        self._downloads.remove(entry_id)

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self._bus.subscribe(listener)

    def run(self, stop: threading.Event) -> None:
        """Reads every profiled game that starts, one at a time, until stop is set."""
        sources = source_plugins()
        sinks: list[Sink] = [TtsSink(self._narrator), self._subtitles, BusSink(self._bus)]
        logger.info("Watching for %s", ", ".join(profile.game.title for profile in self._profiles))
        while not stop.is_set():
            games = find_running_games(self._profiles)
            if not games:
                stop.wait(GAME_CHECK_SECONDS)
                continue
            game = games[0]
            self._enter(game)
            self._ducker.watch(game.process)
            if self._overlay_dirs:
                inject_overlay(game.process.pid, self._overlay_dirs)
            routes = build_routes(
                game, sources, self._stages, self._report, self.is_stage_enabled, self.is_source_enabled, self.languages
            )
            if routes:
                logger.info("Reading %s aloud", game.profile.game.title)
            elif not game.profile.sources:
                logger.warning("%s is running, but its profile has no sources to read yet.", game.profile.game.title)
            else:
                logger.error("%s is running, but none of its sources could start.", game.profile.game.title)
            read_game(game, routes, sinks, stop, self._report, self._is_running, languages=self.languages)
            logger.info("%s closed", game.profile.game.title)
            self._ducker.watch(None)
            self._leave()

    def close(self) -> None:
        self._narrator.close()
        self._preview.close()
        self._ducker.close()
        self._subtitles.close()

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
            inactive=inactive_reason(plugin, self.languages()) if plugin is not None else None,
        )

    def _voice_for(self, language: str, preferred: str) -> str | None:
        """An installed voice for an output language: preferred if it is installed and speaks it,
        else the one last chosen for the language, else the first that speaks it; None if none does.
        """
        matching = [voice.id for voice in self.voices() if primary_language(voice.language) == language]
        remembered = self._shared.voices_by_language.get(language)
        for voice in (preferred, remembered):
            if voice in matching:
                return voice
        return matching[0] if matching else None

    def _speak(self) -> None:
        """While a game is read, speaks with an installed voice for its output language, or not at
        all if there is none; voices are never downloaded here. With no game, the voice is only
        remembered."""
        voice = self._voice_for(self._settings.output_language, self._settings.voice)
        if voice is not None:
            self._narrator.use_voice(voice)
        if self._game is None:
            return
        if voice is None:
            self._narrator.close()
            logger.info("No voice for the output language %s: lines are not spoken", self._settings.output_language)
        else:
            self._narrator.start()

    @_serialized
    def _downloaded(self, event: DownloadEvent) -> None:
        """A download moved on. Once a voice or model is installed or removed, it is used (or no
        longer) right away: a game being read may now be spoken, or need another voice."""
        self._bus.publish(event)
        if event.state in ("installed", "removed"):
            self._speak()
            self._publish_status()

    def _speaking(self, active: bool) -> None:
        """The narrator started speaking or fell silent: the game's sound and the subtitle follow."""
        self._ducker.speaking(active)
        self._subtitles.speaking(active)

    @_serialized
    def _enter(self, game: RunningGame) -> None:
        """A game is being read from now on, with its settings; its voice is loaded only now."""
        self._game = GameInfo(title=game.profile.game.title, pid=game.process.pid)
        self._profile = game.profile
        self._use(load_game(self._settings_dir, game.profile.id))
        self._speak()
        self._publish_status()

    @_serialized
    def _leave(self) -> None:
        """The game is no longer read; its voice is unloaded and the defaults apply again."""
        self._game = None
        self._profile = None
        self._narrator.close()
        self._use(GameSettings())
        self._publish_status()

    def _use(self, settings: GameSettings) -> None:
        """Switches to a game's settings, or to the defaults."""
        self._settings = settings
        if settings.voice != self._narrator.voice:
            self._narrator.use_voice(settings.voice)
        self._narrator.configure(settings.speech_rate, settings.cut_off_lines)
        self._ducker.configure(settings.ducking, settings.duck_volume)
        self._subtitles.configure(settings.subtitles)

    def _change(self, **changes: Any) -> None:
        """Changes settings, saved for the game being read, if any."""
        self._settings = replace(self._settings, **changes)
        profile = self._profile
        if profile is not None:
            save_game(self._settings, self._settings_dir, profile.id)

    def _report(self, error: ErrorEvent) -> None:
        # A source usually fails a moment before the game's exit is noticed; that is not an error.
        game = self._game
        if error.kind == "source.error" and game is not None and self._exits(game.pid):
            logger.debug("Ignoring %s from %s: the game has exited", error.kind, error.origin)
            return
        log_error(error)
        self._bus.publish(error)

    def _exits(self, pid: int) -> bool:
        """Whether the game exits within the grace time. Blocks the caller (the runner) meanwhile,
        which happens only on a source's first failure."""
        deadline = time.monotonic() + self._exit_grace_seconds
        while self._is_running(pid):
            if time.monotonic() >= deadline:
                return False
            time.sleep(EXIT_CHECK_SECONDS)
        return True

    def _publish_status(self) -> Status:
        status = self.status()
        self._bus.publish(status)
        return status


class NoProfilesError(Exception):
    """There is no game profile to watch for."""


def run(profiles_dir: Path, settings_dir: Path, overlay_dirs: Sequence[Path], stop: threading.Event) -> None:
    """Starts the core and its API, and runs until stop is set or the process is interrupted."""
    profiles, errors = load_profiles(profiles_dir) if profiles_dir.is_dir() else ([], [])
    for error in errors:
        logger.error("Skipping a profile: %s", error)
    if not profiles:
        raise NoProfilesError(f"No game profiles in {profiles_dir}. Copy a profile there or pass --profiles.")

    core = Core(profiles, settings_dir, overlay_dirs)
    server = ApiServer(core)
    try:
        server.start()
        core.run(stop)
    finally:
        server.stop()
        core.close()
