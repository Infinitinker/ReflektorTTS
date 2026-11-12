"""The sources of the app being read that fail, which its status shows until they work again; and
whether a source failed only because its app was exiting."""

import time
from collections.abc import Callable

from reflektortts.events import ErrorEvent

EXIT_CHECK_SECONDS = 0.1


class SourceErrors:
    """The failing sources, by name, in the order they failed, each with its last error."""

    def __init__(self) -> None:
        self._errors: dict[str, ErrorEvent] = {}

    def clear(self) -> None:
        self._errors = {}

    def failed(self, error: ErrorEvent) -> None:
        """A source failed: its error is now the last one."""
        self._errors.pop(error.origin, None)
        self._errors[error.origin] = error

    def fails_again(self, error: ErrorEvent) -> bool:
        """A failing source fails for another reason now: that becomes its error, and the last
        one. Whether it was failing."""
        if self._errors.pop(error.origin, None) is None:
            return False
        self._errors[error.origin] = error
        return True

    def works_again(self, origin: str) -> bool:
        """A source works again. Whether it was failing."""
        return self._errors.pop(origin, None) is not None

    def last(self) -> ErrorEvent | None:
        return next(reversed(self._errors.values()), None)


def exits_within(pid: int, seconds: float, is_running: Callable[[int], bool]) -> bool:
    """Whether a process exits within seconds; blocks the caller meanwhile."""
    deadline = time.monotonic() + seconds
    while is_running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(EXIT_CHECK_SECONDS)
    return True
