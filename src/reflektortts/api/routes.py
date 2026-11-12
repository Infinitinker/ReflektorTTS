"""The /v1 routes: a handler for each request, which asks the core and answers in JSON, and the app
that routes requests to them."""

import asyncio
import weakref
from collections.abc import Callable
from dataclasses import asdict

from aiohttp import WSMsgType, web

from reflektortts.api.bodies import (
    DOWNLOADS_HELP,
    IMPORT_HELP,
    INTEGRATION_HELP,
    OUTPUTS,
    PROFILES_HELP,
    SETTING_CHECKS,
    SETTINGS_HELP,
    SOURCES_HELP,
    STAGES_HELP,
    read_object,
    settings_change,
)
from reflektortts.api.control import CoreControl
from reflektortts.api.encoders import (
    event_json,
    integration_json,
    listed_json,
    profile_json,
    profile_settings_json,
    status_json,
)
from reflektortts.api.errors import json_errors
from reflektortts.api.guard import refuse_web_pages
from reflektortts.bus import Event
from reflektortts.downloads.manager import Listing
from reflektortts.downloads.source import DownloadError, DownloadStateError, UnknownDownloadError
from reflektortts.events import Output, ProfileSettingsView
from reflektortts.integrations import IntegrationError, UnknownIntegrationError
from reflektortts.languages import LANGUAGES, LanguageError
from reflektortts.profiles.catalog import ProfileChangeError, ProfileExistsError
from reflektortts.profiles.errors import BrokenProfileError, SourceError, StageError, UnknownProfileError
from reflektortts.profiles.loader import ProfileError
from reflektortts.tts.engine import VoiceError

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
    languages = sorted(LANGUAGES.values(), key=lambda language: language.english_name)
    return web.json_response(
        {
            "languages": [
                {"code": language.code, "name": language.name, "english_name": language.english_name}
                for language in languages
            ]
        }
    )


async def profile_settings_response(
    request: web.Request, act: Callable[[CoreControl, str], ProfileSettingsView]
) -> web.Response:
    """Runs act on the core with the profile ID in the path, off the event loop (the core may wait
    for a TTS process while it holds its lock), and answers with the profile's settings."""
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


async def get_integrations(request: web.Request) -> web.Response:
    views = await asyncio.to_thread(request.app[CORE].integrations)
    return web.json_response({"integrations": [integration_json(view) for view in views]})


async def patch_integration(request: web.Request) -> web.Response:
    body = await read_object(request)
    if body is None or not isinstance(body.get("enabled"), bool):
        return error_response(INTEGRATION_HELP)
    try:
        view = await asyncio.to_thread(
            request.app[CORE].set_integration_enabled, request.match_info["id"], body["enabled"]
        )
    except UnknownIntegrationError as error:
        return error_response(str(error), 404)
    except IntegrationError as error:
        return error_response(str(error), 409)
    return web.json_response(integration_json(view))


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
            web.get("/v1/integrations", get_integrations),
            web.patch("/v1/integrations/{id}", patch_integration),
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
