"""The desktop app's side of the local API: follows the core's status and sends it commands."""

import asyncio
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable

import aiohttp

from reflektortts.api.server import HOST, PORT
from reflektortts.desktop.status import CoreStatus, parse_status

logger = logging.getLogger(__name__)

BASE_URL = f"http://{HOST}:{PORT}/v1"
RETRY_SECONDS = 1.0
TIMEOUT_SECONDS = 5.0


class ApiClientError(Exception):
    """The core did not take a command."""


def post(path: str, base_url: str = BASE_URL) -> None:
    """Sends a command without a body, e.g. post("/pause")."""
    request = urllib.request.Request(f"{base_url}{path}", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except (urllib.error.URLError, OSError) as error:
        raise ApiClientError(f"ReflektorTTS did not respond: {error}") from error


class StatusFeed:
    """Follows /v1/events on a thread of its own and passes each status to on_status, or None
    while the core does not answer (still starting, or stopped). It reconnects until stopped.
    on_status is called on that thread.
    """

    def __init__(self, on_status: Callable[[CoreStatus | None], None], base_url: str = BASE_URL) -> None:
        self._on_status = on_status
        self._url = f"{base_url}/events"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping: asyncio.Event | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._follow()), name="status feed", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait()

    def stop(self) -> None:
        if self._loop is not None and self._stopping is not None:
            self._loop.call_soon_threadsafe(self._stopping.set)
        self._thread.join()

    async def _follow(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        self._ready.set()
        async with aiohttp.ClientSession() as session:
            while not self._stopping.is_set():
                following = asyncio.create_task(self._follow_once(session))
                stopping = asyncio.create_task(self._stopping.wait())
                await asyncio.wait({following, stopping}, return_when=asyncio.FIRST_COMPLETED)
                following.cancel()
                stopping.cancel()
                if not self._stopping.is_set():
                    self._on_status(None)
                    try:
                        await asyncio.wait_for(self._stopping.wait(), RETRY_SECONDS)
                    except TimeoutError:
                        pass

    async def _follow_once(self, session: aiohttp.ClientSession) -> None:
        try:
            async with session.ws_connect(self._url, heartbeat=30) as socket:
                async for message in socket:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        break
                    status = parse_status(json.loads(message.data))
                    if status is not None:
                        self._on_status(status)
        except (aiohttp.ClientError, OSError) as error:
            logger.debug("Status feed not connected: %s", error)
