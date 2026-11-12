"""A profile's settings as the API shows them, the changes that switch its sources and stages, and
the voice they speak with: functions of the profile, its settings and the plugins, which change
nothing themselves."""

from collections.abc import Mapping, Sequence

from reflektortts.core.reading import stage_key, stage_on
from reflektortts.events import Output, ProfileSettingsView, SourceStages, StageState
from reflektortts.languages import Languages, primary_language
from reflektortts.pipeline.plugins import StagePlugin, inactive_reason
from reflektortts.profiles.errors import SourceError, StageError
from reflektortts.profiles.model import Profile, StageSettings
from reflektortts.settings import ProfileSettings
from reflektortts.tts.engine import VoiceInfo


def stage_switch(settings: ProfileSettings, key: str, output: Output) -> bool | None:
    """How the user switched a stage for an output, or None if they have not."""
    return settings.stage_switches.get(key, {}).get(output)


def languages_of(settings: ProfileSettings) -> Languages:
    return Languages(input=settings.input_language, output=settings.output_language)


def switched(disabled: tuple[str, ...], key: str, enabled: bool) -> tuple[str, ...]:
    """Switched-off keys, with key switched on or off."""
    return tuple(sorted(set(disabled) - {key} if enabled else set(disabled) | {key}))


def with_source_switched(profile: Profile, settings: ProfileSettings, name: str, enabled: bool) -> ProfileSettings:
    """The settings with a source switched on or off. Raises SourceError if the profile has no such source."""
    names = [source.name for source in profile.sources]
    if name not in names:
        raise SourceError(f'{profile.app.title} has no source "{name}". Its sources: {", ".join(names)}.')
    return ProfileSettings(**{**vars(settings), "disabled_sources": switched(settings.disabled_sources, name, enabled)})


def with_stage_switched(
    profile: Profile, settings: ProfileSettings, key: str, output: Output, enabled: bool
) -> ProfileSettings:
    """The settings with a stage switched on or off for an output; from then on the profile no
    longer decides it. Raises StageError if the profile has no such stage."""
    keys = [
        stage_key(source.name, position, stage.type)
        for source in profile.sources
        for position, stage in enumerate(source.stages)
    ]
    if key not in keys:
        raise StageError(f'{profile.app.title} has no stage "{key}". Its stages: {", ".join(keys)}.')
    switches = dict(settings.stage_switches)
    switches[key] = switches.get(key, {}) | {output: enabled}
    return ProfileSettings(**{**vars(settings), "stage_switches": switches})


def stage_state(
    key: str, stage: StageSettings, settings: ProfileSettings, plugins: Mapping[str, StagePlugin]
) -> StageState:
    plugin = plugins.get(stage.type)
    return StageState(
        key=key,
        type=stage.type,
        summary=plugin.summary if plugin is not None else "",
        warning=plugin.warning_when_disabled if plugin is not None else None,
        enabled={output: stage_on(stage, output, stage_switch(settings, key, output)) for output in Output},
        inactive=inactive_reason(plugin, languages_of(settings)) if plugin is not None else None,
    )


def source_stages(
    profile: Profile, settings: ProfileSettings, plugins: Mapping[str, StagePlugin]
) -> tuple[SourceStages, ...]:
    return tuple(
        SourceStages(
            source=source.name,
            type=source.type,
            enabled=source.name not in settings.disabled_sources,
            stages=tuple(
                stage_state(stage_key(source.name, position, stage.type), stage, settings, plugins)
                for position, stage in enumerate(source.stages)
            ),
        )
        for source in profile.sources
    )


def settings_view(
    profile: Profile, settings: ProfileSettings, running: bool, voice: str, plugins: Mapping[str, StagePlugin]
) -> ProfileSettingsView:
    """voice is the one the settings speak with (see voice_for)."""
    return ProfileSettingsView(
        profile=profile.id,
        app_title=profile.app.title,
        running=running,
        voice=voice,
        input_language=settings.input_language,
        output_language=settings.output_language,
        ducking=settings.ducking,
        duck_volume=settings.duck_volume,
        speech_rate=settings.speech_rate,
        new_line=settings.new_line,
        subtitles=settings.subtitles,
        subtitle_size=settings.subtitle_size,
        subtitle_position=settings.subtitle_position,
        sources=source_stages(profile, settings, plugins),
    )


def voice_for(voices: Sequence[VoiceInfo], language: str, preferred: str, remembered: str | None) -> str | None:
    """An installed voice for an output language: preferred if it is installed and speaks it, else
    the one last chosen for the language (remembered), else the first that speaks it; None if none
    does."""
    matching = [voice.id for voice in voices if primary_language(voice.language) == language]
    for voice in (preferred, remembered):
        if voice in matching:
            return voice
    return matching[0] if matching else None
