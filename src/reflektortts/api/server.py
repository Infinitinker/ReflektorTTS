"""The local API's server: serves the /v1 routes over HTTP and WebSocket on 127.0.0.1, on its own thread."""

import asyncio
import logging
import threading

from aiohttp import web

from reflektortts.api.control import CoreControl
from reflektortts.api.routes import create_app

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"


class ApiError(Exception):
    """The API server cannot start."""


class ApiServer:
    """Serves the API on a background thread with its own event loop."""

    def __init__(self, core: CoreControl, port: int, host: str = HOST) -> None:
        """port is this ReflektorTTS's (identity.api_port), or 0 for any free one."""
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
