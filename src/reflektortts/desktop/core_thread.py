"""Runs the core and its local API on a background thread, until the app quits."""

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from reflektortts.core import run

logger = logging.getLogger(__name__)

type RunCore = Callable[[Path, Path, Sequence[Path], threading.Event], None]


class CoreThread:
    def __init__(
        self, profiles_dir: Path, settings_dir: Path, overlay_dirs: Sequence[Path], run_core: RunCore = run
    ) -> None:
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(
            target=self._run, args=(run_core, profiles_dir, settings_dir, overlay_dirs), name="core", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """Stops the core and waits for it, which takes up to a few seconds while it reads an app."""
        self._stop.set()
        self._thread.join()

    def stopped(self) -> bool:
        """Whether the core has stopped, on its own (see error) or because stop was called."""
        return not self._thread.is_alive()

    @property
    def error(self) -> Exception | None:
        """Why the core stopped on its own, e.g. ApiError when ReflektorTTS is already running."""
        return self._error

    def _run(self, run_core: RunCore, profiles_dir: Path, settings_dir: Path, overlay_dirs: Sequence[Path]) -> None:
        try:
            run_core(profiles_dir, settings_dir, overlay_dirs, self._stop)
        except Exception as error:
            logger.exception("ReflektorTTS stopped")
            self._error = error
