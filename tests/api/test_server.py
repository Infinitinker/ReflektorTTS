"""The API's server: it runs on its own thread and reports a port another program holds."""

import json
import time
import urllib.request

import pytest

from reflektortts.api.server import ApiError, ApiServer
from tests.api.fake_core import FakeCore


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
