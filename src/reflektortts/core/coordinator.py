"""The core's state and the changes to it: the app being read, the settings, the narrator and the
event bus, which the local API and the watcher change one at a time; and run, which starts the core
and its API."""

import functools
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Concatenate

import psutil

from reflektortts.api.server import ApiServer
from reflektortts.apps.detector import RunningApp
from reflektortts.bus import EventBus, Listener
from reflektortts.core.integration_control import IntegrationControl, load_integrations
from reflektortts.core.profile_settings import (
    languages_of,
    settings_view,
    source_stages,
    stage_switch,
    switched,
    voice_for,
    with_source_switched,
    with_stage_switched,
)
from reflektortts.core.profile_states import profile_views, used_profiles
from reflektortts.core.source_errors import SourceErrors, exits_within
from reflektortts.core.watching import Watcher
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
    Status,
    UnsupportedApp,
)
from reflektortts.identity import API_PORTS, INSTALLED, api_port
from reflektortts.integrations import Integration, IntegrationView
from reflektortts.languages import LanguageError, Languages, check_language, primary_language, sample
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, source_plugins, speech_rules, stage_plugins
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import log_error
from reflektortts.profiles.catalog import (
    CatalogEntry,
    ProfileFiles,
    ProfileState,
    ProfileStore,
    ProfileView,
    Standing,
    choose,
)
from reflektortts.profiles.errors import BrokenProfileError, UnknownProfileError
from reflektortts.profiles.model import Profile
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
from reflektortts.user_dirs import cache_dir, state_dir

logger = logging.getLogger(__name__)

EXIT_GRACE_SECONDS = 2.0
"""How long a source error waits for the app to exit before it is reported: while an app exits,
its memory is torn down before Windows counts the process as gone, so sources fail first."""
INTEGRATIONS_FOLDER = "integrations"
"""In the state folder: one JSON file per integration, named after it, that it may keep its state in."""


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


def _serialized[**P, R](method: Callable[Concatenate["Core", P], R]) -> Callable[Concatenate["Core", P], R]:
    """Runs a Core method holding the core's lock, so changes from the API, the core thread and
    downloads are made one at a time, each in full, and a status is never half old, half new."""

    @functools.wraps(method)
    def serialized(core: "Core", /, *args: P.args, **kwargs: P.kwargs) -> R:
        with core._lock:
            return method(core, *args, **kwargs)

    return serialized


class Core:
    """Owns the narrator, the settings and the event bus; the API controls it through these methods,
    and the watcher (see watching.py) tells it which app is read.

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
        api_port: int = API_PORTS[INSTALLED],
        narrator_factory: Callable[[str, Callable[[bool], None]], Narrator] = start_narrator,
        list_voices: Callable[[], list[VoiceInfo]] = available_voices,
        is_running: Callable[[int], bool] = psutil.pid_exists,
        stages: Mapping[str, StagePlugin] | None = None,
        open_app_volume: Callable[[], OpenAppVolume] = app_volume,
        duck_records: DuckRecords | None = None,
        exit_grace_seconds: float = EXIT_GRACE_SECONDS,
        download_sources: Mapping[str, DownloadSource] | None = None,
        preview_factory: Callable[[Callable[[PreviewEvent], None]], VoicePreview] = VoicePreview,
        sources: Mapping[str, SourcePlugin] | None = None,
        integrations: Mapping[str, Integration] | None = None,
    ) -> None:
        """sources and stages default to the installed plugins, integrations to those of the
        sources, with their files in the state folder. api_port is the local API's, which the
        overlay is told to connect to."""
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
        self._list_voices = list_voices
        self._stages = stage_plugins() if stages is None else stages
        sources = source_plugins() if sources is None else sources
        if integrations is None:
            integrations = load_integrations(sources, state_dir() / INTEGRATIONS_FOLDER)
        self._integrations = IntegrationControl(integrations)
        self._source_errors = SourceErrors()
        """The sources of the app being read that failed and have not worked since."""
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
        downloads = load_download_sources() if download_sources is None else download_sources
        self._downloads = Downloads(downloads, self._downloaded)
        self._preview = preview_factory(self._bus.publish)
        self._watcher = Watcher(self, sources, self._stages, overlay_dirs, api_port, is_running, self._ducker.watch)

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
            sources=() if self._profile is None else source_stages(self._profile, settings, self._stages),
            unsupported=self._unsupported,
            source_error=self._source_errors.last(),
        )

    def languages(self) -> Languages:
        return languages_of(self._settings)

    def voices(self) -> list[VoiceInfo]:
        return self._list_voices()

    def speech_rules(self) -> dict[str, tuple[str, ...]]:
        return speech_rules(self._stages.values())

    def preview_voice(self, voice: str) -> None:
        """Speaks a sample sentence in the voice's language, or the language's name, also while an
        app is read."""
        language = primary_language(find_voice(voice, self.voices()).language)
        try:
            text = sample(language)
        except LanguageError as error:
            raise VoiceError(f'"{voice}" speaks "{language}", a language ReflektorTTS does not know.') from error
        self._preview.play(voice, text)

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
        if change.voice is not None and voice_language is not None:
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
        return self._save(profile, with_source_switched(profile, self._settings_of(profile), name, enabled))

    def stage_switch(self, key: str, output: Output) -> bool | None:
        """How the user switched a stage of the app being read for an output, or None if they have not."""
        return stage_switch(self._settings, key, output)

    @_serialized
    def set_stage_enabled(self, profile_id: str, key: str, output: Output, enabled: bool) -> ProfileSettingsView:
        """Switches a profile's stage on or off for an output; see _save. From then on the profile
        no longer decides it. Raises UnknownProfileError, BrokenProfileError, or StageError if the
        profile has no such stage."""
        profile = self._find_profile(profile_id)
        return self._save(profile, with_stage_switched(profile, self._settings_of(profile), key, output, enabled))

    @_serialized
    def profiles(self) -> list[ProfileView]:
        """Every profile, with why it is not used or what its app is doing."""
        return profile_views(
            self._choices,
            self._integrations.states(),
            None if self._profile is None else self._profile.id,
            self._unsupported_profile,
            self._integrations.names,
        )

    @_serialized
    def set_profile_enabled(self, profile_id: str, enabled: bool) -> Status:
        """Enables or disables a profile, saved for the user. A disabled profile's app is not
        watched, and stops being read at once; which profiles clash is decided again."""
        self._check_profile(profile_id)
        disabled = switched(self._shared.disabled_profiles, profile_id, enabled)
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

    @_serialized
    def integrations(self) -> list[IntegrationView]:
        """Every integration, by ID, with its state now."""
        return self._integrations.views()

    @_serialized
    def set_integration_enabled(self, integration_id: str, enabled: bool) -> IntegrationView:
        """Enables or disables an integration; a profile it sets up is read from the next check on.
        Raises UnknownIntegrationError, or IntegrationError with what to do, e.g. for one that is
        unavailable."""
        self._integrations.set_enabled(integration_id, enabled)
        self._log_choices()
        self._publish_status()
        return self._integrations.view(integration_id)

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
        sinks: dict[Output, list[Sink]] = {
            Output.TEXT: [self._subtitles, BusSink(self._bus)],
            Output.SPEECH: [TtsSink(self._narrator)],
        }
        self._log_choices()
        self._watcher.run(stop, sinks)

    def close(self) -> None:
        self._narrator.close()
        self._preview.close()
        self._ducker.close()
        self._subtitles.close()

    @_serialized
    def used_profiles(self) -> list[Profile]:
        """The profiles whose apps are read: used, and set up."""
        return used_profiles(self._choices, self._integrations.states())

    @_serialized
    def enter(self, app: RunningApp) -> None:
        """An app is being read from now on, with its settings; its voice is loaded only now."""
        self._app = AppInfo(title=app.profile.app.title, pid=app.process.pid, profile=app.profile.id)
        self._profile = app.profile
        self._source_errors.clear()
        self._use(load_profile_settings(self._settings_dir, app.profile.id))
        self._speak()
        self._publish_status()

    @_serialized
    def leave(self) -> None:
        """The app is no longer read; its voice is unloaded and the defaults apply again."""
        self._app = None
        self._profile = None
        self._source_errors.clear()
        self._narrator.close()
        self._use(ProfileSettings())
        self._speak()
        self._publish_status()

    @_serialized
    def set_unsupported(self, unsupported: UnsupportedApp | None, profile_id: str | None) -> None:
        """An app runs in a build its profile does not support, until it exits."""
        self._unsupported = unsupported
        self._unsupported_profile = profile_id
        self._publish_status()

    def report(self, error: ErrorEvent) -> None:
        """An error from the app being read: logged and published; a source's is shown in the
        status until it works again."""
        # A source usually fails a moment before the app's exit is noticed; that is not an error.
        app = self._app
        if (
            error.kind == "source.error"
            and app is not None
            and exits_within(app.pid, self._exit_grace_seconds, self._is_running)
        ):
            logger.debug("Ignoring %s from %s: the app has exited", error.kind, error.origin)
            return
        log_error(error)
        self._bus.publish(error)
        if error.kind == "source.error":
            self._source_failed(error)

    @_serialized
    def still_failing(self, error: ErrorEvent) -> None:
        """A failing source of the app being read fails for another reason now: the status says
        that one instead. The app is not checked for exiting, since the first error was."""
        if error.kind == "source.error" and self._source_errors.fails_again(error):
            self._publish_status()

    @_serialized
    def works_again(self, kind: str, origin: str) -> None:
        if kind == "source.error" and self._source_errors.works_again(origin):
            self._publish_status()

    @_serialized
    def _source_failed(self, error: ErrorEvent) -> None:
        """A source of the app being read failed: the status shows it until it works again."""
        if self._app is None:
            return
        self._source_errors.failed(error)
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

    def _log_choices(self) -> None:
        for choice in self._choices:
            if choice.standing in (Standing.BROKEN, Standing.CLASH, Standing.NOT_USED):
                logger.error("Not using the profile %s: %s", choice.entry.id, choice.reason)
        for view in self.profiles():
            if view.state is ProfileState.NOT_SET_UP:
                logger.info("Not reading %s: %s", view.choice.entry.id, view.choice.reason)
        titles = [profile.app.title for profile in self.used_profiles()]
        logger.info("Watching for %s", ", ".join(titles) if titles else "nothing: no profile is used")

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
        voice = self._voice_for(settings.output_language, settings.voice) or settings.voice
        return settings_view(profile, settings, self._is_read(profile.id), voice, self._stages)

    def _voice_for(self, language: str, preferred: str) -> str | None:
        """An installed voice for an output language; see voice_for."""
        return voice_for(self.voices(), language, preferred, self._shared.voices_by_language.get(language))

    def _speak(self) -> None:
        """While an app is read, speaks with an installed voice for its output language, or not at
        all if there is none; voices are never downloaded here. With no app, the voice is only
        remembered."""
        voice = self._voice_for(self._settings.output_language, self._settings.voice)
        if voice is None:
            # Closed first, so that taking the chosen voice starts no TTS process for it.
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

    def _use(self, settings: ProfileSettings) -> None:
        """Switches to an app's settings, or to the defaults; _speak then switches the voice."""
        self._settings = settings
        self._narrator.configure(settings.speech_rate, settings.new_line)
        self._ducker.configure(settings.ducking, settings.duck_volume)
        self._subtitles.configure(settings.subtitles)

    def _publish_status(self) -> Status:
        status = self.status()
        self._bus.publish(status)
        return status


def run(profiles_dir: Path, settings_dir: Path, overlay_dirs: Sequence[Path], stop: threading.Event) -> None:
    """Starts the core and its API, and runs until stop is set or the process is interrupted.
    profiles_dir holds the user's own profiles, next to the bundled ones."""
    port = api_port()
    core = Core(ProfileStore(profiles_dir), settings_dir, overlay_dirs, port)
    server = ApiServer(core, port)
    try:
        server.start()
        core.run(stop)
    finally:
        server.stop()
        core.close()
