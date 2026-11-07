"""HTTP + WebSocket server for the /v1 API, running on its own thread."""

import asyncio
import logging
import threading
import weakref
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from aiohttp import WSMsgType, web

from reflektortts.api.errors import json_errors
from reflektortts.api.guard import refuse_web_pages
from reflektortts.bus import Event, Listener
from reflektortts.downloads.manager import Listed, Listing
from reflektortts.downloads.source import DownloadError, DownloadStateError, UnknownDownloadError
from reflektortts.events import (
    DownloadEvent,
    ErrorEvent,
    Output,
    PreviewEvent,
    ProfileSettingsView,
    SourceStages,
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
)
from reflektortts.languages import LANGUAGES, LanguageError
from reflektortts.profiles.catalog import ProfileChangeError, ProfileExistsError, ProfileView
from reflektortts.profiles.loader import ProfileError
from reflektortts.settings import SettingsChange
from reflektortts.sinks.subtitles import POSITIONS, SIZES
from reflektortts.tts.engine import MAX_RATE, MIN_RATE, VoiceError, VoiceInfo
from reflektortts.tts.service import NewLine

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 47821
"""Fixed so the overlay knows where to connect."""


class ApiError(Exception):
    """The API server cannot start."""


class SourceError(Exception):
    """A source cannot be switched on or off; the message says why."""


class StageError(Exception):
    """A stage cannot be switched on or off; the message says why."""


class UnknownProfileError(Exception):
    """There is no profile with that ID."""


class BrokenProfileError(Exception):
    """A profile's file cannot be read, so it has no settings to show or change."""


class CoreControl(Protocol):
    """What the API needs from the core. Every method on a profile's settings raises
    UnknownProfileError if there is no such profile, and BrokenProfileError if its file cannot be
    read."""

    def status(self) -> Status: ...

    def voices(self) -> list[VoiceInfo]: ...

    def preview_voice(self, voice: str) -> None:
        """Raises VoiceError if the voice is not available or speaks no supported language."""

    def profile_settings(self, profile_id: str) -> ProfileSettingsView: ...

    def change_profile_settings(self, profile_id: str, change: SettingsChange) -> ProfileSettingsView:
        """Raises LanguageError for a language that is not supported, VoiceError for a voice that is
        not available; then nothing is changed."""

    def set_source_enabled(self, profile_id: str, name: str, enabled: bool) -> ProfileSettingsView:
        """Raises SourceError if the profile has no such source."""

    def set_stage_enabled(self, profile_id: str, key: str, output: Output, enabled: bool) -> ProfileSettingsView:
        """Raises StageError if the profile has no such stage."""

    def set_paused(self, paused: bool) -> Status: ...

    def stop_line(self) -> Status: ...

    def profiles(self) -> list[ProfileView]: ...

    def set_profile_enabled(self, profile_id: str, enabled: bool) -> Status:
        """Raises UnknownProfileError if there is no such profile."""

    def import_profile(self, profile_id: str, data: Any, replace: bool) -> Status:
        """Raises ProfileError, ProfileExistsError or ProfileChangeError."""

    def copy_profile(self, profile_id: str) -> Path:
        """Raises UnknownProfileError or ProfileChangeError."""

    def remove_profile(self, profile_id: str) -> Status:
        """Raises UnknownProfileError or ProfileChangeError."""

    def reload_profiles(self) -> Status: ...

    def downloads(self, refresh: bool) -> Listing:
        """refresh fetches the lists from the internet, so it can take a while."""

    def start_download(self, entry_id: str) -> None:
        """Raises DownloadError if it cannot start."""

    def remove_download(self, entry_id: str) -> None:
        """Raises DownloadError if it cannot be removed."""

    def subscribe(self, listener: Listener) -> Callable[[], None]: ...


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
    return {
        "type": "status",
        "app": None if app is None else {"title": app.title, "pid": app.pid, "profile": app.profile},
        "unsupported": None if unsupported is None else {"title": unsupported.title, "sha256": unsupported.sha256},
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


CORE = web.AppKey("core", CoreControl)
SOCKETS = web.AppKey("sockets", weakref.WeakSet[web.WebSocketResponse])


def error_response(message: str, status: int = 400) -> web.Response:
    """400 for a request that is wrong as sent; 404 for a resource in the path that does not exist;
    409 for one that cannot be done as things are now, e.g. with a broken profile file."""
    return web.json_response({"error": message}, status=status)


async def get_status(request: web.Request) -> web.Response:
    return web.json_response(status_json(await asyncio.to_thread(request.app[CORE].status)))


async def get_voices(request: web.Request) -> web.Response:
    voices = await asyncio.to_thread(request.app[CORE].voices)
    return web.json_response({"voices": [asdict(voice) for voice in voices]})


async def get_languages(request: web.Request) -> web.Response:
    return web.json_response({"languages": [{"code": code, "name": name} for code, name in LANGUAGES.items()]})


SETTINGS_HELP = (
    'Send any of "input_language", "output_language" and "voice" (text), "ducking" and "subtitles" (true or '
    'false), "duck_volume" (a number from 0 to 1), "speech_rate" (a number from 0.5 to 2), "new_line" ("wait", '
    '"cut_off" or "speed_up"), "subtitle_size" ("small", "medium" or "large") and "subtitle_position" ("top" or '
    '"bottom"), e.g. {"output_language": "pl"}.'
)
SOURCES_HELP = 'Send {"name": "<source name from the profile\'s settings>", "enabled": true or false}.'
OUTPUTS = tuple(output.value for output in Output)
STAGES_HELP = (
    'Send {"key": "<stage key from the profile\'s settings>", "output": "text" or "speech", "enabled": true or false}.'
)
PROFILES_HELP = 'Send {"id": "<id from GET /v1/profiles>", "enabled": true or false}.'
IMPORT_HELP = 'Send {"id": "<the file name without .json>", "profile": {<the profile>}, "replace": true or false}.'


async def read_object(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def is_fraction(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


def is_rate(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and MIN_RATE <= value <= MAX_RATE


def is_text(value: object) -> bool:
    return isinstance(value, str)


def is_flag(value: object) -> bool:
    return isinstance(value, bool)


SETTING_CHECKS: dict[str, Callable[[object], bool]] = {
    "input_language": is_text,
    "output_language": is_text,
    "voice": is_text,
    "ducking": is_flag,
    "duck_volume": is_fraction,
    "speech_rate": is_rate,
    "new_line": lambda value: value in tuple(NewLine),
    "subtitles": is_flag,
    "subtitle_size": lambda value: value in SIZES,
    "subtitle_position": lambda value: value in POSITIONS,
}


def settings_change(values: dict[str, Any]) -> SettingsChange:
    """A change from settings checked with SETTING_CHECKS."""
    fields = dict(values)
    for field in ("duck_volume", "speech_rate"):
        if field in fields:
            fields[field] = float(fields[field])
    if "new_line" in fields:
        fields["new_line"] = NewLine(fields["new_line"])
    return SettingsChange(**fields)


async def profile_settings_response(
    request: web.Request, act: Callable[[CoreControl, str], ProfileSettingsView]
) -> web.Response:
    """Runs act on the core with the profile ID in the path, off the event loop (the core may wait
    for a speech process while it holds its lock), and answers with the profile's settings."""
    try:
        view = await asyncio.to_thread(act, request.app[CORE], request.match_info["id"])
    except UnknownProfileError as error:
        return error_response(str(error), 404)
    except BrokenProfileError as error:
        return error_response(str(error), 409)
    except (VoiceError, LanguageError, SourceError, StageError) as error:
        return error_response(str(error))
    return web.json_response(profile_settings_json(view))


async def get_profile_settings(request: web.Request) -> web.Response:
    return await profile_settings_response(request, lambda core, profile_id: core.profile_settings(profile_id))


async def patch_profile_settings(request: web.Request) -> web.Response:
    """Each setting is optional; the core checks the languages and the voice, and applies a request
    in full or not at all."""
    body = await read_object(request)
    if body is None:
        return error_response("The request body must be a JSON object.")
    unknown = [field for field in body if field not in SETTING_CHECKS]
    if unknown:
        return error_response(f'There is no setting "{unknown[0]}". {SETTINGS_HELP}')
    wrong = [field for field, value in body.items() if not SETTING_CHECKS[field](value)]
    if not body or wrong:
        return error_response(f'"{wrong[0]}" cannot be set to that. {SETTINGS_HELP}' if wrong else SETTINGS_HELP)
    change = settings_change(body)
    return await profile_settings_response(
        request, lambda core, profile_id: core.change_profile_settings(profile_id, change)
    )


async def patch_profile_sources(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("name"), str) or not isinstance(body.get("enabled"), bool):
        return error_response(SOURCES_HELP)
    name, enabled = body["name"], body["enabled"]
    return await profile_settings_response(
        request, lambda core, profile_id: core.set_source_enabled(profile_id, name, enabled)
    )


async def patch_profile_stages(request: web.Request) -> web.Response:
    body = await read_object(request)
    if (
        body is None
        or not isinstance(body.get("key"), str)
        or body.get("output") not in OUTPUTS
        or not isinstance(body.get("enabled"), bool)
    ):
        return error_response(STAGES_HELP)
    key, output, enabled = body["key"], Output(body["output"]), body["enabled"]
    return await profile_settings_response(
        request, lambda core, profile_id: core.set_stage_enabled(profile_id, key, output, enabled)
    )


async def get_profiles(request: web.Request) -> web.Response:
    views = await asyncio.to_thread(request.app[CORE].profiles)
    return web.json_response({"profiles": [profile_json(view) for view in views]})


async def patch_profiles(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("id"), str) or not isinstance(body.get("enabled"), bool):
        return error_response(PROFILES_HELP)
    try:
        status = await asyncio.to_thread(request.app[CORE].set_profile_enabled, body["id"], body["enabled"])
    except UnknownProfileError as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def post_profiles(request: web.Request) -> web.Response:
    body = await read_object(request)
    replace = body.get("replace", False) if body is not None else None
    if body is None or not isinstance(body.get("id"), str) or "profile" not in body or not isinstance(replace, bool):
        return error_response(IMPORT_HELP)
    try:
        status = await asyncio.to_thread(request.app[CORE].import_profile, body["id"], body["profile"], replace)
    except ProfileExistsError as error:
        return error_response(str(error), 409)
    except (ProfileError, ProfileChangeError) as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def post_profile_copy(request: web.Request) -> web.Response:
    try:
        path = await asyncio.to_thread(request.app[CORE].copy_profile, request.match_info["id"])
    except UnknownProfileError as error:
        return error_response(str(error), 404)
    except ProfileChangeError as error:
        return error_response(str(error), 409)
    return web.json_response({"file": str(path)})


async def delete_profile(request: web.Request) -> web.Response:
    try:
        status = await asyncio.to_thread(request.app[CORE].remove_profile, request.match_info["id"])
    except UnknownProfileError as error:
        return error_response(str(error), 404)
    except ProfileChangeError as error:
        return error_response(str(error), 409)
    return web.json_response(status_json(status))


async def post_profiles_reload(request: web.Request) -> web.Response:
    status = await asyncio.to_thread(request.app[CORE].reload_profiles)
    return web.json_response(status_json(status))


DOWNLOADS_HELP = 'Send {"id": "<id from GET /v1/downloads>"}.'


async def downloads_response(request: web.Request, refresh: bool) -> web.Response:
    listing: Listing = await asyncio.to_thread(request.app[CORE].downloads, refresh)
    return web.json_response(
        {"entries": [listed_json(listed) for listed in listing.entries], "errors": list(listing.errors)}
    )


async def get_downloads(request: web.Request) -> web.Response:
    return await downloads_response(request, refresh=False)


async def post_downloads_refresh(request: web.Request) -> web.Response:
    """A POST, not a GET: fetching the lists reaches the internet, and a web page can send GETs
    that the guard cannot tell from ReflektorTTS's own."""
    return await downloads_response(request, refresh=True)


async def post_downloads(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("id"), str):
        return error_response(DOWNLOADS_HELP)
    try:
        await asyncio.to_thread(request.app[CORE].start_download, body["id"])
    except DownloadStateError as error:
        return error_response(str(error), 409)
    except DownloadError as error:
        return error_response(str(error))
    return web.json_response({"id": body["id"]}, status=202)


async def delete_download(request: web.Request) -> web.Response:
    entry_id = request.match_info["id"]
    try:
        await asyncio.to_thread(request.app[CORE].remove_download, entry_id)
    except UnknownDownloadError as error:
        return error_response(str(error), 404)
    except DownloadStateError as error:
        return error_response(str(error), 409)
    except DownloadError as error:
        return error_response(str(error))
    return web.json_response({"id": entry_id})


async def post_pause(request: web.Request) -> web.Response:
    return web.json_response(status_json(await asyncio.to_thread(request.app[CORE].set_paused, True)))


async def post_resume(request: web.Request) -> web.Response:
    return web.json_response(status_json(await asyncio.to_thread(request.app[CORE].set_paused, False)))


async def post_stop(request: web.Request) -> web.Response:
    return web.json_response(status_json(await asyncio.to_thread(request.app[CORE].stop_line)))


async def post_voice_preview(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("voice"), str):
        return error_response('Send {"voice": "<id from GET /v1/voices>"}.')
    try:
        await asyncio.to_thread(request.app[CORE].preview_voice, body["voice"])
    except VoiceError as error:
        return error_response(str(error))
    return web.json_response({"voice": body["voice"]}, status=202)


async def events(request: web.Request) -> web.WebSocketResponse:
    """Sends the current status, then every core event, until the client disconnects."""
    socket = web.WebSocketResponse(heartbeat=30)
    await socket.prepare(request)
    core = request.app[CORE]
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Event] = asyncio.Queue()

    def forward(event: Event) -> None:
        # Events come from core threads; the queue belongs to this event loop.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    unsubscribe = core.subscribe(forward)
    request.app[SOCKETS].add(socket)

    async def send_events() -> None:
        await socket.send_json(status_json(await asyncio.to_thread(core.status)))
        while True:
            await socket.send_json(event_json(await queue.get()))

    sender = asyncio.create_task(send_events())
    try:
        async for message in socket:
            if message.type == WSMsgType.ERROR:
                break
    finally:
        sender.cancel()
        unsubscribe()
        request.app[SOCKETS].discard(socket)
    return socket


async def close_sockets(app: web.Application) -> None:
    sockets = app[SOCKETS]
    for socket in list(sockets):
        await socket.close()


def create_app(core: CoreControl) -> web.Application:
    app = web.Application(middlewares=[json_errors, refuse_web_pages])
    app[CORE] = core
    app[SOCKETS] = weakref.WeakSet()
    app.add_routes(
        [
            web.get("/v1/status", get_status),
            web.get("/v1/voices", get_voices),
            web.post("/v1/voices/preview", post_voice_preview),
            web.get("/v1/languages", get_languages),
            web.get("/v1/profiles", get_profiles),
            web.patch("/v1/profiles", patch_profiles),
            web.post("/v1/profiles", post_profiles),
            web.post("/v1/profiles/reload", post_profiles_reload),
            web.post("/v1/profiles/{id}/copy", post_profile_copy),
            web.delete("/v1/profiles/{id}", delete_profile),
            web.get("/v1/profiles/{id}/settings", get_profile_settings),
            web.patch("/v1/profiles/{id}/settings", patch_profile_settings),
            web.patch("/v1/profiles/{id}/sources", patch_profile_sources),
            web.patch("/v1/profiles/{id}/stages", patch_profile_stages),
            web.post("/v1/pause", post_pause),
            web.post("/v1/resume", post_resume),
            web.post("/v1/stop", post_stop),
            web.get("/v1/downloads", get_downloads),
            web.post("/v1/downloads", post_downloads),
            web.post("/v1/downloads/refresh", post_downloads_refresh),
            web.delete("/v1/downloads/{id}", delete_download),
            web.get("/v1/events", events),
        ]
    )
    app.on_shutdown.append(close_sockets)
    return app


class ApiServer:
    """Serves the API on a background thread with its own event loop."""

    def __init__(self, core: CoreControl, host: str = HOST, port: int = PORT) -> None:
        self._core = core
        self._host = host
        self._port = port
        self._ready = threading.Event()
        self._error: OSError | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping: asyncio.Event | None = None
        self._thread = threading.Thread(target=lambda: asyncio.run(self._serve()), name="api", daemon=True)
        self.port = port

    def start(self) -> None:
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            raise ApiError(
                f"Cannot open the local API on {self._host}:{self._port} ({self._error.strerror}). "
                "Is ReflektorTTS already running?"
            ) from self._error
        logger.info("Local API listening on http://%s:%d/v1", self._host, self.port)

    def stop(self) -> None:
        """Stops serving; after a failed start, the server has stopped already and its loop may be
        closed, so there is nothing to tell it."""
        if self._error is None and self._loop is not None and self._stopping is not None:
            self._loop.call_soon_threadsafe(self._stopping.set)
        self._thread.join()

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        runner = web.AppRunner(create_app(self._core))
        await runner.setup()
        try:
            await web.TCPSite(runner, self._host, self._port).start()
        except OSError as error:
            self._error = error
            self._ready.set()
            await runner.cleanup()
            return
        self.port = runner.addresses[0][1]
        self._ready.set()
        await self._stopping.wait()
        await runner.cleanup()
