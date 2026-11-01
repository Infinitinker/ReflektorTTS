from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestClient

from tests.api.test_server import FakeCore, with_client


def test_requests_from_web_pages_are_refused() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.post("/v1/pause", headers={"Origin": "https://example.invalid"})
        assert (response.status, await response.json()) == (
            403,
            {"error": "ReflektorTTS does not accept requests from web pages."},
        )
        status = await client.get("/v1/status", headers={"Origin": "null"})
        assert status.status == 403

    with_client(core, test)
    assert not core.current.paused


def test_a_web_page_cannot_listen_to_the_events() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        with pytest.raises(aiohttp.WSServerHandshakeError) as refused:
            await client.ws_connect("/v1/events", origin="https://example.invalid")
        assert refused.value.status == 403

    with_client(FakeCore(), test)


def test_requests_to_another_host_name_are_refused() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/status", headers={"Host": "attacker.invalid:47821"})
        assert (response.status, await response.json()) == (
            403,
            {"error": 'Send requests to 127.0.0.1 or localhost, not "attacker.invalid:47821".'},
        )
        assert (await client.get("/v1/status", headers={"Host": "localhost:47821"})).status == 200

    with_client(FakeCore(), test)


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_a_body_that_is_not_json_is_refused(content_type: str) -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/settings", data='{"ducking": false}', headers={"Content-Type": content_type})
        assert (response.status, await response.json()) == (
            415,
            {"error": 'Send the body as JSON, with "Content-Type: application/json".'},
        )

    with_client(core, test)
    assert core.current.ducking


def test_the_clients_own_requests_pass() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await client.patch("/v1/settings", json={"ducking": False})).status == 200
        assert (await client.post("/v1/pause")).status == 200
        async with client.ws_connect("/v1/events") as socket:
            assert (await socket.receive_json())["type"] == "status"

    with_client(core, test)
    assert not core.current.ducking
