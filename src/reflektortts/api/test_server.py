import asyncio
import json
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from reflektortts.api.server import SETTINGS_HELP, ApiError, ApiServer, create_app
from reflektortts.bus import EventBus, Listener
from reflektortts.events import ErrorEvent, GameInfo, Status, TextEvent
from reflektortts.languages import LanguageError
from reflektortts.tts.engine import VoiceError, VoiceInfo

ADAM = VoiceInfo(id="windows:Microsoft Adam", engine="windows", name="Microsoft Adam", language="pl-PL")


class FakeCore:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.current = Status(game=GameInfo("Grand Theft Auto 2", 42), voice="piper:a", language="en", paused=False)

    def status(self) -> Status:
        return self.current

    def voices(self) -> list[VoiceInfo]:
        return [ADAM]

    def set_voice(self, voice: str) -> Status:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.current = replace(self.current, voice=voice)
        return self.current

    def set_language(self, language: str) -> Status:
        if language not in ("en", "pl"):
            raise LanguageError(f'There is no language "{language}".')
        self.current = replace(self.current, language=language)
        return self.current

    def set_paused(self, paused: bool) -> Status:
        self.current = replace(self.current, paused=paused)
        return self.current

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
            "voice": "piper:a",
            "language": "en",
            "paused": False,
        }

    with_client(FakeCore(), test)


def test_languages() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        languages = (await (await client.get("/v1/languages")).json())["languages"]
        assert {"code": "pl", "name": "Polski"} in languages

    with_client(FakeCore(), test)


def test_changing_the_language_and_voice_together() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/settings", json={"language": "pl", "voice": "windows:Microsoft Adam"})
        body = await response.json()
        assert (body["language"], body["voice"]) == ("pl", "windows:Microsoft Adam")

    with_client(FakeCore(), test)


def test_voices() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/voices")
        assert await response.json() == {
            "voices": [
                {"id": "windows:Microsoft Adam", "engine": "windows", "name": "Microsoft Adam", "language": "pl-PL"}
            ]
        }

    with_client(FakeCore(), test)


def test_changing_the_voice() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/settings", json={"voice": "windows:Microsoft Adam"})
        assert response.status == 200
        assert (await response.json())["voice"] == "windows:Microsoft Adam"

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"voice": "piper:missing"}, 'There is no voice "piper:missing".'),
        ({"language": "xx"}, 'There is no language "xx".'),
        ({"voice": 5}, SETTINGS_HELP),
        ({"volume": 5}, SETTINGS_HELP),
        ("not json", "The request body must be JSON."),
    ],
)
def test_bad_settings_are_rejected_with_a_message(body: Any, message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        if isinstance(body, str):
            response = await client.patch("/v1/settings", data=body)
        else:
            response = await client.patch("/v1/settings", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_pause_and_resume() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        assert (await (await client.post("/v1/pause")).json())["paused"] is True
        assert (await (await client.post("/v1/resume")).json())["paused"] is False

    with_client(FakeCore(), test)


def test_events_start_with_the_status_then_follow_the_core() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        socket = await client.ws_connect("/v1/events")
        first = await socket.receive_json(timeout=2)
        core.bus.publish(TextEvent("messages", "Welcome to Downtown", 1.0))
        core.bus.publish(ErrorEvent("source.error", "messages", "game closed"))
        line = await socket.receive_json(timeout=2)
        error = await socket.receive_json(timeout=2)
        await socket.close()

        assert first["type"] == "status"
        assert line == {"type": "line", "source": "messages", "text": "Welcome to Downtown"}
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
    finally:
        server.stop()
