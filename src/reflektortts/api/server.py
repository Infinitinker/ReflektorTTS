"""HTTP + WebSocket server for the /v1 API, running on its own thread."""

import asyncio
import logging
import threading
import weakref
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Protocol

from aiohttp import WSMsgType, web

from reflektortts.bus import Event, Listener
from reflektortts.events import ErrorEvent, StageState, Status, SubtitleEvent, TextEvent
from reflektortts.languages import LANGUAGES, LanguageError
from reflektortts.sinks.subtitles import POSITIONS, SIZES
from reflektortts.tts.engine import MAX_RATE, MIN_RATE, VoiceError, VoiceInfo

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 47821
"""Fixed so the in-game overlay knows where to connect."""


class ApiError(Exception):
    """The API server cannot start."""


class SourceError(Exception):
    """A source cannot be switched on or off; the message says why."""


class StageError(Exception):
    """A stage cannot be switched on or off; the message says why."""


class CoreControl(Protocol):
    """What the API needs from the core."""

    def status(self) -> Status: ...

    def voices(self) -> list[VoiceInfo]: ...

    def set_voice(self, voice: str) -> Status:
        """Raises VoiceError if the voice is not available."""

    def set_game_language(self, language: str) -> Status:
        """Raises LanguageError if the language is not supported."""

    def set_output_language(self, language: str) -> Status:
        """Raises LanguageError if the language is not supported."""

    def set_ducking(self, enabled: bool, volume: float) -> Status:
        """volume is the game's volume while speaking, from 0.0 to 1.0 of its own."""

    def set_speech(self, rate: float, cut_off: bool) -> Status:
        """rate is from MIN_RATE to MAX_RATE."""

    def set_subtitles(self, enabled: bool, size: str, position: str) -> Status:
        """size is one of SIZES, position one of POSITIONS."""

    def set_paused(self, paused: bool) -> Status: ...

    def stop_line(self) -> Status: ...

    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        """Raises SourceError if no game is read or it has no such source."""

    def set_stage_enabled(self, key: str, enabled: bool) -> Status:
        """Raises StageError if no game is read or it has no such stage."""

    def subscribe(self, listener: Listener) -> Callable[[], None]: ...


def stage_json(stage: StageState) -> dict[str, Any]:
    return {
        "key": stage.key,
        "type": stage.type,
        "summary": stage.summary,
        "warning": stage.warning,
        "enabled": stage.enabled,
        "inactive": stage.inactive,
    }


def status_json(status: Status) -> dict[str, Any]:
    game = None if status.game is None else {"title": status.game.title, "pid": status.game.pid}
    return {
        "type": "status",
        "game": game,
        "voice": status.voice,
        "game_language": status.game_language,
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
    return status_json(event)


CORE = web.AppKey("core", CoreControl)
SOCKETS = web.AppKey("sockets", weakref.WeakSet[web.WebSocketResponse])


def error_response(message: str) -> web.Response:
    return web.json_response({"error": message}, status=400)


async def get_status(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].status()))


async def get_voices(request: web.Request) -> web.Response:
    voices = await asyncio.to_thread(request.app[CORE].voices)
    return web.json_response({"voices": [asdict(voice) for voice in voices]})


async def get_languages(request: web.Request) -> web.Response:
    return web.json_response({"languages": [{"code": code, "name": name} for code, name in LANGUAGES.items()]})


SETTINGS_HELP = (
    'Send any of "game_language", "output_language" and "voice" (text), "ducking", "cut_off_lines" and '
    '"subtitles" (true or false), "duck_volume" (a number from 0 to 1), "speech_rate" (a number from 0.5 to 2), '
    '"subtitle_size" ("small", "medium" or "large") and "subtitle_position" ("top" or "bottom"), '
    'e.g. {"output_language": "pl"}.'
)
SOURCES_HELP = 'Send {"name": "<source name from the status>", "enabled": true or false}.'
STAGES_HELP = 'Send {"key": "<stage key from the status>", "enabled": true or false}.'


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
    "game_language": is_text,
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
    """Applies ducking, speech and subtitles, the game language, then the output language, then the voice.

    Each is optional. Changing the output language may also switch the voice, so an explicit voice comes last.
    """
    body = await read_object(request)
    if body is None:
        return error_response("The request body must be a JSON object.")
    values = {field: body[field] for field in SETTING_CHECKS if field in body}
    if not values or any(not SETTING_CHECKS[field](value) for field, value in values.items()):
        return error_response(SETTINGS_HELP)
    core = request.app[CORE]
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
        if "game_language" in values:
            status = core.set_game_language(values["game_language"])
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
    except SourceError as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def patch_stages(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("key"), str) or not isinstance(body.get("enabled"), bool):
        return error_response(STAGES_HELP)
    try:
        status = request.app[CORE].set_stage_enabled(body["key"], body["enabled"])
    except StageError as error:
        return error_response(str(error))
    return web.json_response(status_json(status))


async def post_pause(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].set_paused(True)))


async def post_resume(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].set_paused(False)))


async def post_stop(request: web.Request) -> web.Response:
    return web.json_response(status_json(request.app[CORE].stop_line()))


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
    app = web.Application()
    app[CORE] = core
    app[SOCKETS] = weakref.WeakSet()
    app.add_routes(
        [
            web.get("/v1/status", get_status),
            web.get("/v1/voices", get_voices),
            web.get("/v1/languages", get_languages),
            web.patch("/v1/settings", patch_settings),
            web.patch("/v1/sources", patch_sources),
            web.patch("/v1/stages", patch_stages),
            web.post("/v1/pause", post_pause),
            web.post("/v1/resume", post_resume),
            web.post("/v1/stop", post_stop),
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
        if self._loop is not None and self._stopping is not None:
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
