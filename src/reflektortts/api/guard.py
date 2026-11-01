"""Keeps web pages away from the local API.

A page open in the player's browser can send requests to 127.0.0.1 too, and its WebSocket can
listen to the events. Browsers mark such requests, and ReflektorTTS's own clients never send
those marks, so they are refused:

- an Origin header, which browsers send with cross-site requests and every WebSocket;
- a Host other than 127.0.0.1 or localhost, which is what a page sends after rebinding its own
  domain name to 127.0.0.1 (DNS rebinding);
- a body that is not declared as JSON: pages can send text or form data without asking the API
  first, but not JSON.
"""

from collections.abc import Awaitable, Callable

from aiohttp import web

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
JSON = "application/json"

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def _refused(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


@web.middleware
async def refuse_web_pages(request: web.Request, handler: Handler) -> web.StreamResponse:
    if "Origin" in request.headers:
        return _refused(403, "ReflektorTTS does not accept requests from web pages.")
    if request.url.host not in LOCAL_HOSTS:
        return _refused(403, f'Send requests to 127.0.0.1 or localhost, not "{request.host}".')
    if request.body_exists and request.content_type != JSON:
        return _refused(415, f'Send the body as JSON, with "Content-Type: {JSON}".')
    return await handler(request)
