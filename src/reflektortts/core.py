"""The core: watches for profiled apps, reads them aloud, and answers the local API."""

import functools
import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Concatenate

import psutil

from reflektortts.api.server import ApiServer, BrokenProfileError, SourceError, StageError, UnknownProfileError
from reflektortts.apps.detector import Builds, RunningApp, find_running_apps
from reflektortts.bus import EventBus, Listener
from reflektortts.downloads.manager import Downloads, Listing
from reflektortts.downloads.source import DownloadSource, download_plugins
from reflektortts.ducking.ducker import Ducker
from reflektortts.ducking.records import DuckRecords, records_path
from reflektortts.ducking.volume import DuckingUnavailableError, OpenAppVolume, system_app_volume
from reflektortts.events import (
    AppInfo,
    DownloadEvent,
    ErrorEvent,
    Output,
    PreviewEvent,
    ProfileSettingsView,
    SourceStages,
    StageState,
    Status,
    UnsupportedApp,
)
from reflektortts.languages import (
    DEFAULT_INPUT_LANGUAGE,
    DEFAULT_OUTPUT_LANGUAGE,
    SAMPLES,
    Languages,
    check_language,
    primary_language,
)
from reflektortts.overlay import inject_overlay
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, inactive_reason, source_plugins, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Chain, Route, Runner, log_error
from reflektortts.profiles.catalog import (
    CatalogEntry,
    Choice,
    ProfileFiles,
    ProfileState,
    ProfileStore,
    ProfileView,
    Standing,
    choose,
)
from reflektortts.profiles.model import Profile, SourceSettings, StageSettings
from reflektortts.settings import (
    ProfileSettings,
    SettingsChange,
    changed,
    load_profile_settings,
    load_shared,
    save_profile_settings,
    save_shared,
)
from reflektortts.sinks.bus import BusSink
from reflektortts.sinks.subtitles import Subtitles
from reflektortts.sinks.tts.narrator import Narrator
from reflektortts.sinks.tts.preview import VoicePreview
from reflektortts.sinks.tts.sink import TtsSink
from reflektortts.tts.engine import VoiceError, VoiceInfo, available_voices, find_voice
from reflektortts.user_dirs import cache_dir, data_dir

logger = logging.getLogger(__name__)

APP_CHECK_SECONDS = 2.0
EXIT_GRACE_SECONDS = 2.0
"""How long a source error waits for the app to exit before it is reported: while an app exits,
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


def stage_on(stage: StageSettings, output: Output, switch: bool | None) -> bool:
    """Whether a stage is on for an output: as the user switched it, else as its profile starts it."""
    if switch is not None:
        return switch
    return stage.text if output is Output.TEXT else stage.speech


def _enabled_check(
    source: SourceSettings,
    output: Output,
    plugins: Mapping[str, StagePlugin],
    stage_switch: Callable[[str, Output], bool | None],
    languages: Callable[[], Languages],
) -> Callable[[int], bool]:
    """Whether the stage at a position runs for an output: it is on there, and it works with the
    user's languages."""
    stages = source.stages
    return lambda position: (
        stage_on(
            stages[position], output, stage_switch(stage_key(source.name, position, stages[position].type), output)
        )
        and inactive_reason(plugins[stages[position].type], languages()) is None
    )


def _source_check(source: str, is_source_enabled: Callable[[str], bool]) -> Callable[[], bool]:
    return lambda: is_source_enabled(source)


def _stage_switch(settings: ProfileSettings, key: str, output: Output) -> bool | None:
    """How the user switched a stage for an output, or None if they have not."""
    return settings.stage_switches.get(key, {}).get(output)


def _languages(settings: ProfileSettings) -> Languages:
    return Languages(input=settings.input_language, output=settings.output_language)


def _switched(disabled: tuple[str, ...], key: str, enabled: bool) -> tuple[str, ...]:
    """Switched-off keys, with key switched on or off."""
    return tuple(sorted(set(disabled) - {key} if enabled else set(disabled) | {key}))


def build_routes(
    app: RunningApp,
    sources: Mapping[str, SourcePlugin],
    stages: Mapping[str, StagePlugin],
    on_error: Callable[[ErrorEvent], None],
    stage_switch: Callable[[str, Output], bool | None] = lambda key, output: None,
    is_source_enabled: Callable[[str], bool] = lambda name: True,
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
) -> list[Route]:
    """Creates the app's sources and, for each output, their stages; a source that cannot start,
    or one of whose stages cannot, is reported and skipped.

    stage_switch tells, by stage key and output, how the user switched the stage, or None if they
    have not; is_source_enabled tells whether the user has a source, by name, switched on. A stage
    that does nothing with the user's languages is skipped too.
    """
    routes = []
    for settings in app.profile.sources:
        try:
            source = sources[settings.type].create(settings, app)
        except Exception as error:
            on_error(ErrorEvent("source.error", settings.name, str(error)))
            continue
        try:
            chains = {
                output: Chain(
                    [stages[stage.type].create(stage.settings, app.profile.glossary) for stage in settings.stages],
                    _enabled_check(settings, output, stages, stage_switch, languages),
                )
                for output in Output
            }
        except Exception as error:
            source.close()
            on_error(ErrorEvent("source.error", settings.name, f"A processing stage cannot start ({error})."))
            continue
        routes.append(Route(source, chains, _source_check(settings.name, is_source_enabled)))
    return routes


def read_app(
    app: RunningApp,
    routes: Sequence[Route],
    sinks: Mapping[Output, Sequence[Sink]],
    stop: threading.Event,
    on_error: Callable[[ErrorEvent], None] = log_error,
    is_running: Callable[[int], bool] = psutil.pid_exists,
    check_seconds: float = APP_CHECK_SECONDS,
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
) -> None:
    """Runs the pipeline until the app exits or stop is set, then closes the sources."""
    runner_stop = threading.Event()
    runner = Runner(routes, sinks, on_error, languages=languages)
    worker = threading.Thread(target=runner.run, args=(runner_stop,), name="runner")
    worker.start()
    try:
        while is_running(app.process.pid) and not stop.wait(check_seconds):
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

    Settings belong to each profile and are saved for it; an app starts with the defaults until
    the user changes something for it. A profile's settings can be changed whether or not its app
    runs; those of the app being read apply at once. While no app is read, the status shows the
    defaults.
    """

    def __init__(
        self,
        profiles: ProfileFiles,
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
        self._profile_files = profiles
        self._catalog = profiles.load()
        self._is_running = is_running
        self._exit_grace_seconds = exit_grace_seconds
        self._settings_dir = settings_dir
        self._shared = load_shared(settings_dir)
        self._choices = choose(self._catalog, self._shared.disabled_profiles)
        self._settings = ProfileSettings()
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
        self._narrator.configure(self._settings.speech_rate, self._settings.new_line)
        self._app: AppInfo | None = None
        self._profile: Profile | None = None
        # With no app, the status shows what a new app starts with: an installed voice for its language.
        self._speak()
        self._unsupported: UnsupportedApp | None = None
        self._unsupported_profile: str | None = None
        self._builds = Builds()
        sources = load_download_sources() if download_sources is None else download_sources
        self._downloads = Downloads(sources, self._downloaded)
        self._preview = preview_factory(self._bus.publish)

    @_serialized
    def status(self) -> Status:
        settings = self._settings
        return Status(
            app=self._app,
            voice=self._narrator.voice,
            input_language=settings.input_language,
            output_language=settings.output_language,
            paused=self._narrator.paused,
            ducking=settings.ducking,
            duck_volume=settings.duck_volume,
            speech_rate=settings.speech_rate,
            new_line=settings.new_line,
            subtitles=settings.subtitles,
            subtitle_size=settings.subtitle_size,
            subtitle_position=settings.subtitle_position,
            sources=() if self._profile is None else self._source_stages(self._profile, settings),
            unsupported=self._unsupported,
        )

    def languages(self) -> Languages:
        return _languages(self._settings)

    def voices(self) -> list[VoiceInfo]:
        return self._list_voices()

    def preview_voice(self, voice: str) -> None:
        """Speaks a sample sentence in the voice's language, also while an app is read."""
        language = primary_language(find_voice(voice, self.voices()).language)
        if language not in SAMPLES:
            raise VoiceError(f'"{voice}" speaks {language}, a language ReflektorTTS does not support.')
        self._preview.play(voice, SAMPLES[language])

    @_serialized
    def profile_settings(self, profile_id: str) -> ProfileSettingsView:
        """A profile's settings, whether or not its app runs. Raises UnknownProfileError, or
        BrokenProfileError for a profile file that cannot be read."""
        profile = self._find_profile(profile_id)
        return self._settings_view(profile, self._settings_of(profile))

    @_serialized
    def change_profile_settings(self, profile_id: str, change: SettingsChange) -> ProfileSettingsView:
        """Changes a profile's settings; see _save. Choosing an output language also switches to a
        voice for it, unless the current one speaks it; any language can be chosen: without a voice
        for it, lines are translated and shown, not spoken. A voice chosen is remembered as the last
        one used for its language. Raises UnknownProfileError, BrokenProfileError, LanguageError or
        VoiceError, and then changes nothing."""
        profile = self._find_profile(profile_id)
        for language in (change.input_language, change.output_language):
            if language is not None:
                check_language(language)
        voice_language = (
            None if change.voice is None else primary_language(find_voice(change.voice, self.voices()).language)
        )
        settings = changed(self._settings_of(profile), change)
        if change.output_language is not None and change.voice is None:
            voice = self._voice_for(settings.output_language, settings.voice)
            settings = replace(settings, voice=voice or settings.voice)
        view = self._save(profile, settings)
        if voice_language is not None:
            # Only once the profile is saved, so a failed save changes nothing.
            remembered = self._shared.voices_by_language | {voice_language: change.voice}
            self._shared = replace(self._shared, voices_by_language=remembered)
            save_shared(self._shared, self._settings_dir)
        return view

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
        """Whether the app being read has a source switched on."""
        return name not in self._settings.disabled_sources

    @_serialized
    def set_source_enabled(self, profile_id: str, name: str, enabled: bool) -> ProfileSettingsView:
        """Switches a profile's source on or off; see _save. Raises UnknownProfileError,
        BrokenProfileError, or SourceError if the profile has no such source."""
        profile = self._find_profile(profile_id)
        names = [source.name for source in profile.sources]
        if name not in names:
            raise SourceError(f'{profile.app.title} has no source "{name}". Its sources: {", ".join(names)}.')
        settings = self._settings_of(profile)
        return self._save(
            profile, replace(settings, disabled_sources=_switched(settings.disabled_sources, name, enabled))
        )

    def stage_switch(self, key: str, output: Output) -> bool | None:
        """How the user switched a stage of the app being read for an output, or None if they have not."""
        return _stage_switch(self._settings, key, output)

    @_serialized
    def set_stage_enabled(self, profile_id: str, key: str, output: Output, enabled: bool) -> ProfileSettingsView:
        """Switches a profile's stage on or off for an output; see _save. From then on the profile
        no longer decides it. Raises UnknownProfileError, BrokenProfileError, or StageError if the
        profile has no such stage."""
        profile = self._find_profile(profile_id)
        keys = [
            stage_key(source.name, position, stage.type)
            for source in profile.sources
            for position, stage in enumerate(source.stages)
        ]
        if key not in keys:
            raise StageError(f'{profile.app.title} has no stage "{key}". Its stages: {", ".join(keys)}.')
        settings = self._settings_of(profile)
        switches = dict(settings.stage_switches)
        switches[key] = switches.get(key, {}) | {output: enabled}
        return self._save(profile, replace(settings, stage_switches=switches))

    @_serialized
    def profiles(self) -> list[ProfileView]:
        """Every profile, with why it is not used or what its app is doing."""
        return [ProfileView(choice, self._profile_state(choice)) for choice in self._choices]

    @_serialized
    def set_profile_enabled(self, profile_id: str, enabled: bool) -> Status:
        """Enables or disables a profile, saved for the user. A disabled profile's app is not
        watched, and stops being read at once; which profiles clash is decided again."""
        self._check_profile(profile_id)
        disabled = _switched(self._shared.disabled_profiles, profile_id, enabled)
        self._shared = replace(self._shared, disabled_profiles=disabled)
        save_shared(self._shared, self._settings_dir)
        self._choices = choose(self._catalog, disabled)
        return self._publish_status()

    @_serialized
    def import_profile(self, profile_id: str, data: Any, replace: bool) -> Status:
        """Adds a profile to the user's own, once checked. Raises ProfileError for a broken one,
        ProfileExistsError if the user has one with that ID and replace is False, and
        ProfileChangeError for an ID that cannot be a file name."""
        self._profile_files.add(profile_id, data, replace)
        return self._reload_profiles()

    @_serialized
    def copy_profile(self, profile_id: str) -> Path:
        """Copies a bundled profile to the user's own, where it replaces the bundled one; returns
        the copy's path. Raises UnknownProfileError or ProfileChangeError."""
        self._check_profile(profile_id)
        path = self._profile_files.copy(profile_id)
        self._reload_profiles()
        return path

    @_serialized
    def remove_profile(self, profile_id: str) -> Status:
        """Deletes the user's own profile file. Raises UnknownProfileError, or ProfileChangeError
        for a bundled one."""
        self._check_profile(profile_id)
        self._profile_files.remove(profile_id)
        return self._reload_profiles()

    @_serialized
    def reload_profiles(self) -> Status:
        """Reads the profile files again, e.g. after the user edited one."""
        return self._reload_profiles()

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
        """Reads every profiled app that starts, one at a time, until stop is set."""
        sources = source_plugins()
        sinks: dict[Output, list[Sink]] = {
            Output.TEXT: [self._subtitles, BusSink(self._bus)],
            Output.SPEECH: [TtsSink(self._narrator)],
        }
        self._log_choices()
        while not stop.is_set():
            apps = sorted(find_running_apps(self._used(), builds=self._builds), key=lambda app: not app.supported)
            if not apps:
                stop.wait(APP_CHECK_SECONDS)
                continue
            app = apps[0]
            if not app.supported:
                self._wait_while_unsupported(app, stop)
                continue
            self._enter(app)
            self._ducker.watch(app.process)
            if app.profile.overlay and self._overlay_dirs:
                inject_overlay(app.process.pid, self._overlay_dirs)
            routes = build_routes(
                app, sources, self._stages, self._report, self.stage_switch, self.is_source_enabled, self.languages
            )
            if routes:
                logger.info("Reading %s aloud", app.profile.app.title)
            elif not app.profile.sources:
                logger.warning("%s is running, but its profile has no sources to read yet.", app.profile.app.title)
            else:
                logger.error("%s is running, but none of its sources could start.", app.profile.app.title)
            read_app(app, routes, sinks, stop, self._report, self._watching(app), languages=self.languages)
            still_running = self._is_running(app.process.pid)
            logger.info("Stopped reading %s" if still_running else "%s closed", app.profile.app.title)
            self._ducker.watch(None, still_running=still_running)
            self._leave()

    def _wait_while_unsupported(self, app: RunningApp, stop: threading.Event) -> None:
        """A build the profile does not list is neither read nor given the overlay; the user is
        told, until it exits."""
        title = app.profile.app.title
        logger.warning(
            "%s is running, but this version of it is not supported yet (%s has SHA-256 %s)",
            title,
            app.process.name,
            app.build or "unknown",
        )
        self._set_unsupported(UnsupportedApp(title, app.build), app.profile.id)
        watching = self._watching(app)
        while not stop.is_set() and watching(app.process.pid):
            stop.wait(APP_CHECK_SECONDS)
        self._set_unsupported(None, None)

    @_serialized
    def _set_unsupported(self, unsupported: UnsupportedApp | None, profile_id: str | None) -> None:
        self._unsupported = unsupported
        self._unsupported_profile = profile_id
        self._publish_status()

    def _check_profile(self, profile_id: str) -> CatalogEntry:
        for entry in self._catalog:
            if entry.id == profile_id:
                return entry
        ids = ", ".join(entry.id for entry in self._catalog)
        raise UnknownProfileError(f'There is no profile "{profile_id}". Profiles: {ids}.')

    def _find_profile(self, profile_id: str) -> Profile:
        """A profile by ID; for the app being read, the one it is read with, even if its file
        changed since."""
        if self._profile is not None and self._profile.id == profile_id:
            return self._profile
        entry = self._check_profile(profile_id)
        if entry.profile is None:
            raise BrokenProfileError(
                f'The profile "{profile_id}" cannot be read ({entry.error}). Fix its file, then reload the profiles.'
            )
        return entry.profile

    def _is_read(self, profile_id: str) -> bool:
        return self._profile is not None and self._profile.id == profile_id

    def _reload_profiles(self) -> Status:
        """Reads the profiles again and decides which are used. An app being read whose profile
        is no longer used stops being read; a changed profile applies when its app starts again."""
        self._catalog = self._profile_files.load()
        self._choices = choose(self._catalog, self._shared.disabled_profiles)
        self._log_choices()
        return self._publish_status()

    def _used(self) -> list[Profile]:
        return [
            choice.entry.profile
            for choice in self._choices
            if choice.entry.profile and choice.standing == Standing.USED
        ]

    def _watching(self, app: RunningApp) -> Callable[[int], bool]:
        """Whether an app is still to be read: it runs, and its profile was not disabled (or
        set aside) meanwhile, which ends reading as if the app had closed."""

        def watching(pid: int) -> bool:
            return self._is_running(pid) and any(profile.id == app.profile.id for profile in self._used())

        return watching

    def _profile_state(self, choice: Choice) -> ProfileState:
        if choice.standing != Standing.USED:
            return ProfileState(choice.standing.value)
        if self._is_read(choice.entry.id):
            return ProfileState.READING
        if self._unsupported_profile == choice.entry.id:
            return ProfileState.UNSUPPORTED
        return ProfileState.NOT_RUNNING

    def _log_choices(self) -> None:
        for choice in self._choices:
            if choice.standing in (Standing.BROKEN, Standing.CLASH, Standing.NOT_USED):
                logger.error("Not using the profile %s: %s", choice.entry.id, choice.reason)
        titles = [profile.app.title for profile in self._used()]
        logger.info("Watching for %s", ", ".join(titles) if titles else "nothing: no profile is used")

    def close(self) -> None:
        self._narrator.close()
        self._preview.close()
        self._ducker.close()
        self._subtitles.close()

    def _settings_of(self, profile: Profile) -> ProfileSettings:
        if self._is_read(profile.id):
            return self._settings
        return load_profile_settings(self._settings_dir, profile.id)

    def _save(self, profile: Profile, settings: ProfileSettings) -> ProfileSettingsView:
        """Saves a profile's settings and publishes them; if its app is being read, they apply at
        once, and the status is published too."""
        save_profile_settings(settings, self._settings_dir, profile.id)
        if self._is_read(profile.id):
            self._use(settings)
            self._speak()
            self._publish_status()
        view = self._settings_view(profile, settings)
        self._bus.publish(view)
        return view

    def _settings_view(self, profile: Profile, settings: ProfileSettings) -> ProfileSettingsView:
        return ProfileSettingsView(
            profile=profile.id,
            app_title=profile.app.title,
            running=self._is_read(profile.id),
            voice=self._voice_for(settings.output_language, settings.voice) or settings.voice,
            input_language=settings.input_language,
            output_language=settings.output_language,
            ducking=settings.ducking,
            duck_volume=settings.duck_volume,
            speech_rate=settings.speech_rate,
            new_line=settings.new_line,
            subtitles=settings.subtitles,
            subtitle_size=settings.subtitle_size,
            subtitle_position=settings.subtitle_position,
            sources=self._source_stages(profile, settings),
        )

    def _source_stages(self, profile: Profile, settings: ProfileSettings) -> tuple[SourceStages, ...]:
        return tuple(
            SourceStages(
                source=source.name,
                type=source.type,
                enabled=source.name not in settings.disabled_sources,
                stages=tuple(
                    self._stage_state(stage_key(source.name, position, stage.type), stage, settings)
                    for position, stage in enumerate(source.stages)
                ),
            )
            for source in profile.sources
        )

    def _stage_state(self, key: str, stage: StageSettings, settings: ProfileSettings) -> StageState:
        plugin = self._stages.get(stage.type)
        return StageState(
            key=key,
            type=stage.type,
            summary=plugin.summary if plugin is not None else "",
            warning=plugin.warning_when_disabled if plugin is not None else None,
            enabled={output: stage_on(stage, output, _stage_switch(settings, key, output)) for output in Output},
            inactive=inactive_reason(plugin, _languages(settings)) if plugin is not None else None,
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
        """While an app is read, speaks with an installed voice for its output language, or not at
        all if there is none; voices are never downloaded here. With no app, the voice is only
        remembered."""
        voice = self._voice_for(self._settings.output_language, self._settings.voice)
        if voice is None:
            # Closed first, so that taking the chosen voice starts no speech process for it.
            self._narrator.close()
            self._narrator.use_voice(self._settings.voice)
            if self._app is not None:
                logger.info("No voice for the output language %s: lines are not spoken", self._settings.output_language)
            return
        self._narrator.use_voice(voice)
        if self._app is not None:
            self._narrator.start()

    @_serialized
    def _downloaded(self, event: DownloadEvent) -> None:
        """A download moved on. Once a voice or model is installed or removed, it is used (or no
        longer) right away: an app being read may now be spoken, or need another voice."""
        self._bus.publish(event)
        if event.state in ("installed", "removed"):
            self._speak()
            self._publish_status()

    def _speaking(self, active: bool) -> None:
        """The narrator started speaking or fell silent: the app's sound and the subtitle follow."""
        self._ducker.speaking(active)
        self._subtitles.speaking(active)

    @_serialized
    def _enter(self, app: RunningApp) -> None:
        """An app is being read from now on, with its settings; its voice is loaded only now."""
        self._app = AppInfo(title=app.profile.app.title, pid=app.process.pid, profile=app.profile.id)
        self._profile = app.profile
        self._use(load_profile_settings(self._settings_dir, app.profile.id))
        self._speak()
        self._publish_status()

    @_serialized
    def _leave(self) -> None:
        """The app is no longer read; its voice is unloaded and the defaults apply again."""
        self._app = None
        self._profile = None
        self._narrator.close()
        self._use(ProfileSettings())
        self._speak()
        self._publish_status()

    def _use(self, settings: ProfileSettings) -> None:
        """Switches to an app's settings, or to the defaults; _speak then switches the voice."""
        self._settings = settings
        self._narrator.configure(settings.speech_rate, settings.new_line)
        self._ducker.configure(settings.ducking, settings.duck_volume)
        self._subtitles.configure(settings.subtitles)

    def _report(self, error: ErrorEvent) -> None:
        # A source usually fails a moment before the app's exit is noticed; that is not an error.
        app = self._app
        if error.kind == "source.error" and app is not None and self._exits(app.pid):
            logger.debug("Ignoring %s from %s: the app has exited", error.kind, error.origin)
            return
        log_error(error)
        self._bus.publish(error)

    def _exits(self, pid: int) -> bool:
        """Whether the app exits within the grace time. Blocks the caller (the runner) meanwhile,
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


def run(profiles_dir: Path, settings_dir: Path, overlay_dirs: Sequence[Path], stop: threading.Event) -> None:
    """Starts the core and its API, and runs until stop is set or the process is interrupted.
    profiles_dir holds the user's own profiles, next to the bundled ones."""
    core = Core(ProfileStore(profiles_dir), settings_dir, overlay_dirs)
    server = ApiServer(core)
    try:
        server.start()
        core.run(stop)
    finally:
        server.stop()
        core.close()
