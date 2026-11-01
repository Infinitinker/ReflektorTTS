import asyncio
import json
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from reflektortts.api.server import (
    SETTINGS_HELP,
    SOURCES_HELP,
    STAGES_HELP,
    ApiError,
    ApiServer,
    SourceError,
    StageError,
    create_app,
)
from reflektortts.bus import EventBus, Listener
from reflektortts.downloads.manager import Listed, Listing, State
from reflektortts.downloads.source import DownloadError, Entry, Kind
from reflektortts.events import (
    DownloadEvent,
    ErrorEvent,
    GameInfo,
    SourceStages,
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
)
from reflektortts.languages import LanguageError, check_language
from reflektortts.tts.engine import VoiceError, VoiceInfo

ADAM = VoiceInfo(
    id="windows:Microsoft Adam", engine="windows", name="Microsoft Adam", language="pl-PL", engine_title="Windows"
)
GOSIA = Entry(
    "piper:pl_PL-gosia-medium",
    Kind.VOICE,
    "pl_PL-gosia-medium",
    ("pl",),
    63,
    "Dataset: CC0",
    "https://x.invalid",
    False,
    "Piper",
)
TRACKER = StageState(
    key="messages/0:tracker",
    type="tracker",
    summary="waits until a line settles",
    warning="Needed.",
    enabled=True,
)


class FakeCore:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.stopped_lines = 0
        self.refreshed: bool | None = None
        self.started: list[str] = []
        self.removed: list[str] = []
        self.previewed: list[str] = []
        self.current = Status(
            game=GameInfo("Grand Theft Auto 2", 42),
            voice="piper:a",
            input_language="pl",
            output_language="en",
            paused=False,
            ducking=True,
            duck_volume=0.3,
            speech_rate=1.0,
            cut_off_lines=False,
            subtitles=False,
            subtitle_size="medium",
            subtitle_position="top",
            sources=(SourceStages("messages", "memory", True, (TRACKER,)),),
        )

    def status(self) -> Status:
        return self.current

    def voices(self) -> list[VoiceInfo]:
        return [ADAM]

    def set_voice(self, voice: str) -> Status:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.current = replace(self.current, voice=voice)
        return self.current

    def preview_voice(self, voice: str) -> None:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.previewed.append(voice)

    def set_input_language(self, language: str) -> Status:
        check_language(language)
        self.current = replace(self.current, input_language=language)
        return self.current

    def set_output_language(self, language: str) -> Status:
        check_language(language)
        self.current = replace(self.current, output_language=language)
        return self.current

    def set_ducking(self, enabled: bool, volume: float) -> Status:
        self.current = replace(self.current, ducking=enabled, duck_volume=volume)
        return self.current

    def set_speech(self, rate: float, cut_off: bool) -> Status:
        self.current = replace(self.current, speech_rate=rate, cut_off_lines=cut_off)
        return self.current

    def set_subtitles(self, enabled: bool, size: str, position: str) -> Status:
        self.current = replace(self.current, subtitles=enabled, subtitle_size=size, subtitle_position=position)
        return self.current

    def set_paused(self, paused: bool) -> Status:
        self.current = replace(self.current, paused=paused)
        return self.current

    def stop_line(self) -> Status:
        self.stopped_lines += 1
        return self.current

    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        if name != "messages":
            raise SourceError(f'Grand Theft Auto 2 has no source "{name}".')
        self.current = replace(self.current, sources=(replace(self.current.sources[0], enabled=enabled),))
        return self.current

    def set_stage_enabled(self, key: str, enabled: bool) -> Status:
        if key != TRACKER.key:
            raise StageError(f'Grand Theft Auto 2 has no stage "{key}".')
        stage = replace(TRACKER, enabled=enabled)
        self.current = replace(self.current, sources=(replace(self.current.sources[0], stages=(stage,)),))
        return self.current

    def downloads(self, refresh: bool) -> Listing:
        self.refreshed = refresh
        return Listing((Listed(GOSIA, State.AVAILABLE),), ("Could not reach the Argos list.",))

    def start_download(self, entry_id: str) -> None:
        if entry_id != GOSIA.id:
            raise DownloadError(f'There is no download "{entry_id}".')
        self.started.append(entry_id)

    def remove_download(self, entry_id: str) -> None:
        if entry_id != GOSIA.id:
            raise DownloadError(f'There is no download "{entry_id}".')
        self.removed.append(entry_id)

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self.bus.subscribe(listener)


def with_client(core: FakeCore, test: Callable[[TestClient[Any, Any]], Awaitable[None]]) -> None:
    async def run() -> None:
        async with TestClient(TestServer(create_app(core))) as client:
            await test(client)

    asyncio.run(run())


def test_status() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/status")
        assert await response.json() == {
            "type": "status",
            "game": {"title": "Grand Theft Auto 2", "pid": 42},
            "unsupported": None,
            "voice": "piper:a",
            "input_language": "pl",
            "output_language": "en",
            "paused": False,
            "ducking": True,
            "duck_volume": 0.3,
            "speech_rate": 1.0,
            "cut_off_lines": False,
            "subtitles": False,
            "subtitle_size": "medium",
            "subtitle_position": "top",
            "sources": [
                {
                    "name": "messages",
                    "type": "memory",
                    "enabled": True,
                    "stages": [
                        {
                            "key": "messages/0:tracker",
                            "type": "tracker",
                            "summary": "waits until a line settles",
                            "warning": "Needed.",
                            "enabled": True,
                            "inactive": None,
                        }
                    ],
                }
            ],
        }

    with_client(FakeCore(), test)


def test_downloads_are_listed_with_their_state_and_errors() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/downloads", params={"refresh": "1"})
        assert await response.json() == {
            "entries": [
                {
                    "id": "piper:pl_PL-gosia-medium",
                    "source_title": "Piper",
                    "kind": "voice",
                    "name": "pl_PL-gosia-medium",
                    "languages": ["pl"],
                    "size": 63,
                    "license": "Dataset: CC0",
                    "page": "https://x.invalid",
                    "state": "available",
                    "done": 0,
                    "total": None,
                }
            ],
            "errors": ["Could not reach the Argos list."],
        }

    with_client(core, test)
    assert core.refreshed is True


def test_a_download_is_started_and_removed_by_id() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        started = await client.post("/v1/downloads", json={"id": GOSIA.id})
        assert started.status == 202
        assert (await client.delete(f"/v1/downloads/{GOSIA.id}")).status == 200
        unknown = await client.post("/v1/downloads", json={"id": "piper:x"})
        assert (unknown.status, (await unknown.json())["error"]) == (400, 'There is no download "piper:x".')
        assert (await client.post("/v1/downloads", json={})).status == 400

    with_client(core, test)
    assert core.started == core.removed == [GOSIA.id]


def test_a_voice_is_previewed_by_id() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await client.post("/v1/voices/preview", json={"voice": ADAM.id})).status == 202
        unknown = await client.post("/v1/voices/preview", json={"voice": "piper:x"})
        assert (unknown.status, (await unknown.json())["error"]) == (400, 'There is no voice "piper:x".')
        assert (await client.post("/v1/voices/preview", json={})).status == 400

    with_client(core, test)
    assert core.previewed == [ADAM.id]


def test_download_progress_comes_as_events() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        async with client.ws_connect("/v1/events") as socket:
            await socket.receive_json()  # The status first.
            core.bus.publish(DownloadEvent(GOSIA.id, "downloading", 30, 63))
            assert await socket.receive_json() == {
                "type": "download",
                "id": GOSIA.id,
                "state": "downloading",
                "done": 30,
                "total": 63,
                "message": "",
            }

    with_client(core, test)


def test_languages() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        languages = (await (await client.get("/v1/languages")).json())["languages"]
        assert {"code": "pl", "name": "Polski"} in languages

    with_client(FakeCore(), test)


def test_voices() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/voices")
        assert await response.json() == {
            "voices": [
                {
                    "id": "windows:Microsoft Adam",
                    "engine": "windows",
                    "name": "Microsoft Adam",
                    "language": "pl-PL",
                    "engine_title": "Windows",
                }
            ]
        }

    with_client(FakeCore(), test)


def test_changing_all_settings_together() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch(
            "/v1/settings", json={"input_language": "en", "output_language": "pl", "voice": "windows:Microsoft Adam"}
        )
        body = await response.json()
        assert (body["input_language"], body["output_language"], body["voice"]) == (
            "en",
            "pl",
            "windows:Microsoft Adam",
        )

    with_client(FakeCore(), test)


def test_ducking_can_be_changed_alone_or_with_its_level() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"duck_volume": 0.5})).json()
        assert (body["ducking"], body["duck_volume"]) == (True, 0.5)
        body = await (await client.patch("/v1/settings", json={"ducking": False})).json()
        assert (body["ducking"], body["duck_volume"]) == (False, 0.5)

    with_client(FakeCore(), test)


def test_speech_rate_and_cutting_off_can_be_changed() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"speech_rate": 1.5})).json()
        assert (body["speech_rate"], body["cut_off_lines"]) == (1.5, False)
        body = await (await client.patch("/v1/settings", json={"cut_off_lines": True})).json()
        assert (body["speech_rate"], body["cut_off_lines"]) == (1.5, True)

    with_client(FakeCore(), test)


def test_subtitles_can_be_switched_on_and_set_up() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"subtitles": True, "subtitle_size": "large"})).json()
        assert (body["subtitles"], body["subtitle_size"], body["subtitle_position"]) == (True, "large", "top")

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"voice": "piper:missing"}, 'There is no voice "piper:missing". Available: windows:Microsoft Adam.'),
        ({"subtitle_size": "huge"}, f'"subtitle_size" cannot be set to that. {SETTINGS_HELP}'),
        ({"speech_rate": 3}, f'"speech_rate" cannot be set to that. {SETTINGS_HELP}'),
        ({"cut_off_lines": "yes"}, f'"cut_off_lines" cannot be set to that. {SETTINGS_HELP}'),
        ({"subtitle_position": "left"}, f'"subtitle_position" cannot be set to that. {SETTINGS_HELP}'),
        ({"subtitles": 1}, f'"subtitles" cannot be set to that. {SETTINGS_HELP}'),
        ({"ducking": "yes"}, f'"ducking" cannot be set to that. {SETTINGS_HELP}'),
        ({"duck_volume": 1.5}, f'"duck_volume" cannot be set to that. {SETTINGS_HELP}'),
        ({"duck_volume": True}, f'"duck_volume" cannot be set to that. {SETTINGS_HELP}'),
        ({"output_language": "auto"}, 'There is no language "auto". Available: en, pl.'),
        ({"input_language": "auto"}, 'There is no language "auto". Available: en, pl.'),
        ({"voice": 5}, f'"voice" cannot be set to that. {SETTINGS_HELP}'),
        ({"volume": 5, "ducking": True}, f'There is no setting "volume". {SETTINGS_HELP}'),
        ({}, SETTINGS_HELP),
        ("not json", "The request body must be a JSON object."),
    ],
)
def test_bad_settings_are_rejected_with_a_message(body: Any, message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        if isinstance(body, str):
            response = await client.patch("/v1/settings", data=body, headers={"Content-Type": "application/json"})
        else:
            response = await client.patch("/v1/settings", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_a_settings_change_with_one_bad_field_changes_nothing() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/settings", json={"ducking": False, "voice": "piper:missing"})
        assert response.status == 400

    with_client(core, test)
    assert core.current.ducking


def test_switching_a_source_off() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/sources", json={"name": "messages", "enabled": False})
        assert (await response.json())["sources"][0]["enabled"] is False

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "signs", "enabled": False}, 'Grand Theft Auto 2 has no source "signs".'),
        ({"name": "messages", "enabled": "no"}, SOURCES_HELP),
        ({"enabled": True}, SOURCES_HELP),
    ],
)
def test_bad_source_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/sources", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_switching_a_stage_off() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/stages", json={"key": "messages/0:tracker", "enabled": False})
        assert (await response.json())["sources"][0]["stages"][0]["enabled"] is False

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"key": "messages/9:x", "enabled": False}, 'Grand Theft Auto 2 has no stage "messages/9:x".'),
        ({"key": "messages/0:tracker", "enabled": "no"}, STAGES_HELP),
        ({"enabled": True}, STAGES_HELP),
    ],
)
def test_bad_stage_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/stages", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_pause_resume_and_stop_line() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await (await client.post("/v1/pause")).json())["paused"] is True
        assert (await (await client.post("/v1/resume")).json())["paused"] is False
        assert (await client.post("/v1/stop")).status == 200

    with_client(core, test)
    assert core.stopped_lines == 1


def test_events_start_with_the_status_then_follow_the_core() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        socket = await client.ws_connect("/v1/events")
        first = await socket.receive_json(timeout=2)
        core.bus.publish(TextEvent("messages", "Welcome to Downtown", 1.0))
        core.bus.publish(SubtitleEvent("Witamy w Downtown"))
        core.bus.publish(ErrorEvent("source.error", "messages", "game closed"))
        line = await socket.receive_json(timeout=2)
        subtitle = await socket.receive_json(timeout=2)
        error = await socket.receive_json(timeout=2)
        await socket.close()

        assert first["type"] == "status"
        assert line == {"type": "line", "source": "messages", "text": "Welcome to Downtown"}
        assert subtitle == {"type": "subtitle", "text": "Witamy w Downtown"}
        assert error == {"type": "error", "kind": "source.error", "origin": "messages", "message": "game closed"}

    with_client(core, test)


def test_server_runs_on_its_own_thread_and_reports_a_busy_port() -> None:
    server = ApiServer(FakeCore(), port=0)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/v1/status", timeout=5) as response:
            assert json.load(response)["voice"] == "piper:a"

        second = ApiServer(FakeCore(), port=server.port)
        with pytest.raises(ApiError, match="Is ReflektorTTS already running"):
            second.start()
        time.sleep(0.5)  # Lets the failed server's loop close, as when the app is slow to stop it.
        second.stop()
    finally:
        server.stop()


def test_language_errors_are_language_errors() -> None:
    with pytest.raises(LanguageError):
        check_language("auto")
