"""The desktop app's side of the local API: follows the core's status and sends it commands."""

import asyncio
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import aiohttp

from reflektortts.api.server import HOST, PORT
from reflektortts.desktop.catalog import DownloadProgress, PreviewState, parse_preview, parse_progress
from reflektortts.desktop.status import CoreStatus, parse_status

logger = logging.getLogger(__name__)

BASE_URL = f"http://{HOST}:{PORT}/v1"
RETRY_SECONDS = 1.0
TIMEOUT_SECONDS = 5.0


class ApiClientError(Exception):
    """The core did not take a command; status is its HTTP status, or None if it did not answer."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


REFRESH_TIMEOUT_SECONDS = 120.0
"""Refreshing the download lists fetches them from the internet."""


def post(path: str, base_url: str = BASE_URL) -> None:
    """Sends a command without a body, e.g. post("/pause")."""
    request_json("POST", path, base_url=base_url)


def request_json(
    method: str, path: str, body: Any = None, base_url: str = BASE_URL, timeout: float = TIMEOUT_SECONDS
) -> Any:
    """Sends a request and returns its JSON answer. A refused request raises ApiClientError with
    the core's message for the user."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read()
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read())["error"]
        except (ValueError, KeyError, TypeError):
            message = str(error)
        raise ApiClientError(message, error.code) from error
    except (urllib.error.URLError, OSError) as error:
        raise ApiClientError(f"ReflektorTTS did not respond: {error}") from error
    return json.loads(text) if text else None


class StatusFeed:
    """Follows /v1/events on a thread of its own and passes each status to on_status, or None
    while the core does not answer (still starting, or stopped), each download event to
    on_download and each preview event to on_preview. It reconnects until stopped. All are called
    on that thread.
    """

    def __init__(
        self,
        on_status: Callable[[CoreStatus | None], None],
        on_download: Callable[[DownloadProgress], None] = lambda progress: None,
        on_preview: Callable[[PreviewState], None] = lambda preview: None,
        base_url: str = BASE_URL,
    ) -> None:
        self._on_status = on_status
        self._on_download = on_download
        self._on_preview = on_preview
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

    def _handle(self, message: str) -> None:
        """Passes an event on; one the window cannot read is logged and skipped, so it cannot end
        the feed."""
        try:
            event = json.loads(message)
            status = parse_status(event)
            progress = parse_progress(event)
            preview = parse_preview(event)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            logger.warning("Ignoring an event the window cannot read (%s): %s", error, message)
            return
        if status is not None:
            self._on_status(status)
        if progress is not None:
            self._on_download(progress)
        if preview is not None:
            self._on_preview(preview)

    async def _follow_once(self, session: aiohttp.ClientSession) -> None:
        try:
            async with session.ws_connect(self._url, heartbeat=30) as socket:
                async for message in socket:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        break
                    self._handle(message.data)
        except (aiohttp.ClientError, OSError) as error:
            logger.debug("Status feed not connected: %s", error)
