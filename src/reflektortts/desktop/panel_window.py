"""Opens the settings window, reflektortts-panel: the overlay's settings panel for one profile, in a
window of its own, so an app can be set up whether or not it runs, and also apps without the overlay.

The window is a program of its own (C++, see native/README.md), started with --profile <id>, and
the --dock-* arguments that open it beside the desktop app's window (dock.py). Each profile has at
most one: asking again while it is open brings it to the front. ReflektorTTS closes them all when it
quits, since they only work while it runs."""

import logging
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from reflektortts.desktop.dock import Dock
from reflektortts.desktop.win32_windows import bring_to_front

PROGRAM = "reflektortts-panel.exe" if sys.platform == "win32" else "reflektortts-panel"

logger = logging.getLogger(__name__)


class Process(Protocol):
    """What PanelWindows needs of a started program; subprocess.Popen has it."""

    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


Launcher = Callable[[list[str]], Process]
Fronter = Callable[[int], bool]
"""Brings a process's window to the front, given its ID; returns whether it did."""


def start_process(command: list[str]) -> Process:
    return subprocess.Popen(command)


def find_program(overlay: Sequence[Path]) -> Path | None:
    """The settings window's program: in a release (a frozen ReflektorTTS.exe), next to
    ReflektorTTS.exe; run from source, in the first overlay build folder that has it (the 64-bit
    build makes it). None where it is not found."""
    folders = [Path(sys.executable).parent] if getattr(sys, "frozen", False) else list(overlay)
    return next((folder / PROGRAM for folder in folders if (folder / PROGRAM).is_file()), None)


def missing_text() -> str:
    """Why there is no settings window, in a sentence for the status bar."""
    if getattr(sys, "frozen", False):
        return (
            f"The settings window, {PROGRAM}, is missing from ReflektorTTS's folder: "
            "install or unpack ReflektorTTS again."
        )
    if sys.platform != "win32":
        return "The settings window is not available on this system yet."
    return "The settings window isn't built, or no --overlay folder has it: see native/README.md."


class PanelWindows:
    """The open settings windows, at most one per profile."""

    def __init__(
        self, program: Path | None, launch: Launcher = start_process, to_front: Fronter = bring_to_front
    ) -> None:
        """program: the settings window's program, None where there is none."""
        self._program = program
        self._launch = launch
        self._to_front = to_front
        self._open: dict[str, Process] = {}
        """Each started window's process, by its profile's ID; some may have closed since."""

    @property
    def missing(self) -> str | None:
        """Why no settings window can be opened, or None when one can."""
        return None if self._program is not None else missing_text()

    def open(self, profile: str, dock: Callable[[], Dock | None] | None = None) -> None:
        """Opens the profile's settings window, where dock says (centered where it says None, or
        without it), or brings it to the front if it is open already; dock is only asked when the
        window opens. Raises OSError when the program cannot be started, and RuntimeError where
        there is none (see missing)."""
        if self._program is None:
            raise RuntimeError("There is no settings window to open.")
        running = self._open.get(profile)
        if running is not None and running.poll() is None:
            if not self._to_front(running.pid):
                logger.info("Cannot bring the settings window for %s to the front", profile)
            return
        command = [str(self._program), "--profile", profile]
        where = dock() if dock is not None else None
        if where is not None:
            command += where.arguments()
        self._open[profile] = self._launch(command)
        logger.info("Opened the settings window for %s", profile)

    def close_all(self) -> None:
        """Closes every settings window still open."""
        for profile, process in self._open.items():
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError as error:
                    # It may have closed meanwhile; the others are closed all the same.
                    logger.warning("Cannot close the settings window for %s: %s", profile, error)
        self._open.clear()
