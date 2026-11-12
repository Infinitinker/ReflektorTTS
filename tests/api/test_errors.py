"""The API's error format: unknown paths and methods, and unexpected errors, are answered in JSON."""

from typing import Any

import pytest
from aiohttp.test_utils import TestClient

from reflektortts.events import Status
from tests.api.test_server import FakeCore, with_client


class BrokenCore(FakeCore):
    def stop_line(self) -> Status:
        raise RuntimeError("the speech process is gone")


def test_an_unknown_path_or_method_is_answered_in_json() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        missing = await client.get("/v1/nothing")
        assert (missing.status, await missing.json()) == (404, {"error": "There is no request GET /v1/nothing."})
        wrong = await client.delete("/v1/status")
        assert wrong.status == 405
        assert (await wrong.json())["error"].startswith("/v1/status does not take DELETE; it takes GET")

    with_client(FakeCore(), test)


def test_an_unexpected_error_is_answered_in_json_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.post("/v1/stop")
        assert (response.status, await response.json()) == (
            500,
            {"error": "Something went wrong in ReflektorTTS (the speech process is gone). See the log for details."},
        )

    with_client(BrokenCore(), test)
    assert "POST /v1/stop failed" in caplog.text
