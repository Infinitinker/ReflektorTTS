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
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
)
from reflektortts.languages import LANGUAGES, LanguageError, check_language
from reflektortts.profiles.catalog import ProfileChangeError, ProfileExistsError, ProfileView
from reflektortts.profiles.loader import ProfileError
from reflektortts.sinks.subtitles import POSITIONS, SIZES
from reflektortts.tts.engine import MAX_RATE, MIN_RATE, VoiceError, VoiceInfo, find_voice

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


class NoAppError(Exception):
    """A source or stage cannot be switched now: no app is being read."""


class CoreControl(Protocol):
    """What the API needs from the core."""

    def status(self) -> Status: ...

    def voices(self) -> list[VoiceInfo]: ...

    def set_voice(self, voice: str) -> Status:
        """Raises VoiceError if the voice is not available."""

    def preview_voice(self, voice: str) -> None:
        """Raises VoiceError if the voice is not available or speaks no supported language."""

    def set_input_language(self, language: str) -> Status:
        """Raises LanguageError if the language is not supported."""

    def set_output_language(self, language: str) -> Status:
        """Raises LanguageError if the language is not supported."""

    def set_ducking(self, enabled: bool, volume: float) -> Status:
        """volume is the app's volume while speaking, from 0.0 to 1.0 of its own."""

    def set_speech(self, rate: float, cut_off: bool) -> Status:
        """rate is from MIN_RATE to MAX_RATE."""

    def set_subtitles(self, enabled: bool, size: str, position: str) -> Status:
        """size is one of SIZES, position one of POSITIONS."""

    def set_paused(self, paused: bool) -> Status: ...

    def stop_line(self) -> Status: ...

    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        """Raises NoAppError if no app is read, SourceError if it has no such source."""

    def set_stage_enabled(self, key: str, output: Output, enabled: bool) -> Status:
        """Raises NoAppError if no app is read, StageError if it has no such stage."""

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


def status_json(status: Status) -> dict[str, Any]:
    app = None if status.app is None else {"title": status.app.title, "pid": status.app.pid}
    unsupported = status.unsupported
    return {
        "type": "status",
        "app": app,
        "unsupported": None if unsupported is None else {"title": unsupported.title, "sha256": unsupported.sha256},
        "voice": status.voice,
        "input_language": status.input_language,
        "output_language": status.output_language,
        "paused": status.paused,
        "ducking": status.ducking,
        "duck_volume": status.duck_volume,
        "speech_rate": status.speech_rate,
        "cut_off_lines": status.cut_off_lines,
        "subtitles": status.subtitles,
        "subtitle_size": status.subtitle_size,
        "subtitle_position": status.subtitle_position,
        "sources": [
            {
                "name": source.source,
                "type": source.type,
                "enabled": source.enabled,
                "stages": [stage_json(stage) for stage in source.stages],
            }
            for source in status.sources
        ],
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
    409 for one that cannot be done as things are now, e.g. with no app being read."""
    return web.json_response({"error": message}, status=status)


async def get_status(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].status()))


async def get_voices(request: web.Request) -> web.Response:
    voices = await asyncio.to_thread(request.app[CORE].voices)
    return web.json_response({"voices": [asdict(voice) for voice in voices]})


async def get_languages(request: web.Request) -> web.Response:
    return web.json_response({"languages": [{"code": code, "name": name} for code, name in LANGUAGES.items()]})


SETTINGS_HELP = (
    'Send any of "input_language", "output_language" and "voice" (text), "ducking", "cut_off_lines" and '
    '"subtitles" (true or false), "duck_volume" (a number from 0 to 1), "speech_rate" (a number from 0.5 to 2), '
    '"subtitle_size" ("small", "medium" or "large") and "subtitle_position" ("top" or "bottom"), '
    'e.g. {"output_language": "pl"}.'
)
SOURCES_HELP = 'Send {"name": "<source name from the status>", "enabled": true or false}.'
OUTPUTS = tuple(output.value for output in Output)
STAGES_HELP = 'Send {"key": "<stage key from the status>", "output": "text" or "speech", "enabled": true or false}.'
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
    "cut_off_lines": is_flag,
    "subtitles": is_flag,
    "subtitle_size": lambda value: value in SIZES,
    "subtitle_position": lambda value: value in POSITIONS,
}


async def patch_settings(request: web.Request) -> web.Response:
    """Applies ducking, speech and subtitles, the input language, then the output language, then the voice.

    Each is optional. Changing the output language may also switch the voice, so an explicit voice comes last.
    Everything is checked before anything is applied, so a request is applied in full or not at all.
    """
    body = await read_object(request)
    if body is None:
        return error_response("The request body must be a JSON object.")
    unknown = [field for field in body if field not in SETTING_CHECKS]
    if unknown:
        return error_response(f'There is no setting "{unknown[0]}". {SETTINGS_HELP}')
    values = dict(body)
    wrong = [field for field, value in values.items() if not SETTING_CHECKS[field](value)]
    if not values or wrong:
        return error_response(f'"{wrong[0]}" cannot be set to that. {SETTINGS_HELP}' if wrong else SETTINGS_HELP)
    core = request.app[CORE]
    try:
        for field in ("input_language", "output_language"):
            if field in values:
                check_language(values[field])
        if "voice" in values:
            find_voice(values["voice"], await asyncio.to_thread(core.voices))
    except (VoiceError, LanguageError) as error:
        return error_response(str(error))
    try:
        status = core.status()
        if values.keys() & {"ducking", "duck_volume"}:
            enabled = values.get("ducking", status.ducking)
            status = core.set_ducking(enabled, float(values.get("duck_volume", status.duck_volume)))
        if values.keys() & {"speech_rate", "cut_off_lines"}:
            status = core.set_speech(
                float(values.get("speech_rate", status.speech_rate)), values.get("cut_off_lines", status.cut_off_lines)
            )
        if values.keys() & {"subtitles", "subtitle_size", "subtitle_position"}:
            status = core.set_subtitles(
                values.get("subtitles", status.subtitles),
                values.get("subtitle_size", status.subtitle_size),
                values.get("subtitle_position", status.subtitle_position),
            )
        if "input_language" in values:
            status = core.set_input_language(values["input_language"])
        if "output_language" in values:
            status = await asyncio.to_thread(core.set_output_language, values["output_language"])
        if "voice" in values:
            status = await asyncio.to_thread(core.set_voice, values["voice"])
    except (VoiceError, LanguageError) as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def patch_sources(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("name"), str) or not isinstance(body.get("enabled"), bool):
        return error_response(SOURCES_HELP)
    try:
        status = request.app[CORE].set_source_enabled(body["name"], body["enabled"])
    except NoAppError as error:
        return error_response(str(error), 409)
    except SourceError as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def patch_stages(request: web.Request) -> web.Response:
    body = await read_object(request)
    if (
        body is None
        or not isinstance(body.get("key"), str)
        or body.get("output") not in OUTPUTS
        or not isinstance(body.get("enabled"), bool)
    ):
        return error_response(STAGES_HELP)
    try:
        status = request.app[CORE].set_stage_enabled(body["key"], Output(body["output"]), body["enabled"])
    except NoAppError as error:
        return error_response(str(error), 409)
    except StageError as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def get_profiles(request: web.Request) -> web.Response:
    views = request.app[CORE].profiles()
    return web.json_response({"profiles": [profile_json(view) for view in views]})


async def patch_profiles(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("id"), str) or not isinstance(body.get("enabled"), bool):
        return error_response(PROFILES_HELP)
    try:
        status = request.app[CORE].set_profile_enabled(body["id"], body["enabled"])
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


async def get_downloads(request: web.Request) -> web.Response:
    refresh = request.query.get("refresh") in ("1", "true")
    listing: Listing = await asyncio.to_thread(request.app[CORE].downloads, refresh)
    return web.json_response(
        {"entries": [listed_json(listed) for listed in listing.entries], "errors": list(listing.errors)}
    )


async def post_downloads(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("id"), str):
        return error_response(DOWNLOADS_HELP)
    try:
        request.app[CORE].start_download(body["id"])
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
    return web.json_response(status_json(request.app[CORE].set_paused(True)))


async def post_resume(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].set_paused(False)))


async def post_stop(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].stop_line()))


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
        await socket.send_json(status_json(core.status()))
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
            web.patch("/v1/settings", patch_settings),
            web.patch("/v1/sources", patch_sources),
            web.patch("/v1/stages", patch_stages),
            web.get("/v1/profiles", get_profiles),
            web.patch("/v1/profiles", patch_profiles),
            web.post("/v1/profiles", post_profiles),
            web.post("/v1/profiles/reload", post_profiles_reload),
            web.post("/v1/profiles/{id}/copy", post_profile_copy),
            web.delete("/v1/profiles/{id}", delete_profile),
            web.post("/v1/pause", post_pause),
            web.post("/v1/resume", post_resume),
            web.post("/v1/stop", post_stop),
            web.get("/v1/downloads", get_downloads),
            web.post("/v1/downloads", post_downloads),
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
