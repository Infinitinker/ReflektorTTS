"""Answers every failed request in the API's error format, {"error": "..."}: also aiohttp's own
refusals (a path that does not exist, a method a path does not take) and unexpected errors, which
are logged with their traceback."""

import logging

from aiohttp import web

from reflektortts.api.guard import Handler

logger = logging.getLogger(__name__)


def _error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


@web.middleware
async def json_errors(request: web.Request, handler: Handler) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPNotFound:
        return _error(404, f"There is no request {request.method} {request.path}.")
    except web.HTTPMethodNotAllowed as error:
        allowed = ", ".join(sorted(error.allowed_methods))
        return _error(405, f"{request.path} does not take {request.method}; it takes {allowed}.")
    except web.HTTPException as error:
        if error.status < 400:
            raise
        return _error(error.status, error.reason)
    except Exception as error:
        logger.exception("%s %s failed", request.method, request.path)
        return _error(500, f"Something went wrong in ReflektorTTS ({error}). See the log for details.")
