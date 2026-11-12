"""Turns the core's views and events into the API's JSON."""

from typing import Any

from reflektortts.bus import Event
from reflektortts.downloads.manager import Listed
from reflektortts.events import (
    DownloadEvent,
    ErrorEvent,
    PreviewEvent,
    ProfileSettingsView,
    SourceStages,
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
)
from reflektortts.integrations import IntegrationView
from reflektortts.profiles.catalog import ProfileView


def stage_json(stage: StageState) -> dict[str, Any]:
    return {
        "key": stage.key,
        "type": stage.type,
        "summary": stage.summary,
        "warning": stage.warning,
        "enabled": {output.value: on for output, on in stage.enabled.items()},
        "inactive": stage.inactive,
    }


def sources_json(sources: tuple[SourceStages, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": source.source,
            "type": source.type,
            "enabled": source.enabled,
            "stages": [stage_json(stage) for stage in source.stages],
        }
        for source in sources
    ]


def status_json(status: Status) -> dict[str, Any]:
    app = status.app
    unsupported = status.unsupported
    source_error = status.source_error
    return {
        "type": "status",
        "app": None if app is None else {"title": app.title, "pid": app.pid, "profile": app.profile},
        "unsupported": None if unsupported is None else {"title": unsupported.title, "sha256": unsupported.sha256},
        "source_error": None
        if source_error is None
        else {"source": source_error.origin, "message": source_error.message},
        "voice": status.voice,
        "input_language": status.input_language,
        "output_language": status.output_language,
        "paused": status.paused,
        "ducking": status.ducking,
        "duck_volume": status.duck_volume,
        "speech_rate": status.speech_rate,
        "new_line": status.new_line,
        "subtitles": status.subtitles,
        "subtitle_size": status.subtitle_size,
        "subtitle_position": status.subtitle_position,
        "sources": sources_json(status.sources),
    }


def profile_settings_json(view: ProfileSettingsView) -> dict[str, Any]:
    return {
        "type": "profile_settings",
        "profile": view.profile,
        "app": {"title": view.app_title},
        "running": view.running,
        "voice": view.voice,
        "input_language": view.input_language,
        "output_language": view.output_language,
        "ducking": view.ducking,
        "duck_volume": view.duck_volume,
        "speech_rate": view.speech_rate,
        "new_line": view.new_line,
        "subtitles": view.subtitles,
        "subtitle_size": view.subtitle_size,
        "subtitle_position": view.subtitle_position,
        "sources": sources_json(view.sources),
    }


def event_json(event: Event) -> dict[str, Any]:
    if isinstance(event, TextEvent):
        return {"type": "line", "source": event.source, "text": event.text}
    if isinstance(event, SubtitleEvent):
        return {"type": "subtitle", "text": event.text}
    if isinstance(event, ErrorEvent):
        return {"type": "error", "kind": event.kind, "origin": event.origin, "message": event.message}
    if isinstance(event, PreviewEvent):
        return {"type": "preview", "voice": event.voice, "playing": event.playing}
    if isinstance(event, DownloadEvent):
        return {
            "type": "download",
            "id": event.entry_id,
            "state": event.state,
            "done": event.done,
            "total": event.total,
            "message": event.message,
        }
    if isinstance(event, ProfileSettingsView):
        return profile_settings_json(event)
    return status_json(event)


def profile_json(view: ProfileView) -> dict[str, Any]:
    entry = view.choice.entry
    profile = entry.profile
    return {
        "id": entry.id,
        "title": None if profile is None else profile.app.title,
        "year": None if profile is None else profile.app.year,
        "origin": entry.origin,
        "state": view.state,
        "reason": view.choice.reason,
        "file": str(entry.path),
        "overlay": None if profile is None else profile.overlay,
        "rating": None if profile is None or profile.rating is None else profile.rating.value,
        "executables": []
        if profile is None
        else [{"name": executable.name, "sha256": list(executable.sha256)} for executable in profile.match.executables],
        "sources": []
        if profile is None
        else [
            {"name": source.name, "type": source.type, "stages": [stage.type for stage in source.stages]}
            for source in profile.sources
        ],
    }


def integration_json(view: IntegrationView) -> dict[str, Any]:
    return {
        "id": view.id,
        "name": view.name,
        "description": view.description,
        "state": view.state.status.value,
        "reason": view.state.reason,
    }


def listed_json(listed: Listed) -> dict[str, Any]:
    entry = listed.entry
    return {
        "id": entry.id,
        "source_title": entry.source_title,
        "kind": entry.kind,
        "name": entry.name,
        "languages": list(entry.languages),
        "size": entry.size,
        "license": entry.license,
        "page": entry.page,
        "state": listed.state,
        "done": listed.done,
        "total": listed.total,
    }
