"""Lowers the game's sound while the narrator speaks, lektor style, and brings it back afterwards."""

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from reflektortts.ducking.records import DuckRecords
from reflektortts.ducking.volume import AppVolume, OpenAppVolume
from reflektortts.games.detector import ProcessInfo

logger = logging.getLogger(__name__)

DEFAULT_LEVEL = 0.3
"""The game's volume while speaking, as a fraction of its own volume."""


@dataclass(frozen=True)
class Timing:
    fade_down: float = 0.15
    hold: float = 0.5
    """How long speech must stay silent before the game comes back, so it does not pump between lines."""
    fade_up: float = 0.4
    step: float = 0.01


DEFAULT_TIMING = Timing()


@dataclass
class _Lowered:
    game: ProcessInfo
    volume: AppVolume
    original: float
    current: float


type _Action = Callable[[_Lowered | None], _Lowered | None]


class Ducker:
    """Fades the watched game down when speech starts and back up once it has been silent for a moment.

    All volume changes happen on a thread of its own. While a game is lowered, its original volume
    is kept in records, so a later run can put it back if this one stops before restoring it.
    """

    def __init__(
        self,
        open_volume: OpenAppVolume,
        records: DuckRecords,
        enabled: bool = True,
        level: float = DEFAULT_LEVEL,
        timing: Timing = DEFAULT_TIMING,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._open_volume = open_volume
        self._records = records
        self._enabled = enabled
        self._level = level
        self._timing = timing
        self._clock = clock
        self._sleep = sleep
        self._changed = threading.Condition()
        self._game: ProcessInfo | None = None
        self._restore_leftover = False
        self._speaking = False
        self._silent_since = -math.inf
        self._stretch = 0
        """Counts stretches of speech, so a game with no sound is looked up once per stretch, not in a loop."""
        self._tried_stretch = 0
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="ducker", daemon=True)
        self._thread.start()

    def watch(self, game: ProcessInfo | None) -> None:
        """Sets the game to lower; None when no game is running."""
        with self._changed:
            self._game = game
            self._restore_leftover = game is not None
            self._changed.notify()

    def speaking(self, active: bool) -> None:
        with self._changed:
            if active and not self._speaking:
                self._stretch += 1
            if not active and self._speaking:
                self._silent_since = self._clock()
            self._speaking = active
            self._changed.notify()

    def configure(self, enabled: bool, level: float) -> None:
        with self._changed:
            self._enabled = enabled
            self._level = level
            self._changed.notify()

    def close(self) -> None:
        """Puts a lowered game's volume back at once and stops the thread."""
        with self._changed:
            self._closed = True
            self._changed.notify()
        self._thread.join()

    def _run(self) -> None:
        lowered: _Lowered | None = None
        while True:
            with self._changed:
                action: _Action | None = None
                while not self._closed:
                    action, timeout = self._decide(lowered)
                    if action is not None:
                        break
                    self._changed.wait(timeout)
            if action is None:
                break
            try:
                lowered = action(lowered)
            except Exception as error:
                # The game may have stopped playing or exited; its record lets a later run restore it.
                logger.warning("Could not change the game's volume: %s", error)
                lowered = None
        if lowered is not None:
            try:
                self._set(lowered, lowered.original)
                self._records.remove(lowered.game.name)
            except Exception as error:
                logger.warning("Could not restore the volume of %s: %s", lowered.game.name, error)

    def _decide(self, lowered: _Lowered | None) -> tuple[_Action | None, float | None]:
        """The next volume change, or None and how long to wait for one. Called with the lock held."""
        game = self._game
        if lowered is not None and (game is None or game.pid != lowered.game.pid):
            return self._forget, None
        if game is None:
            return None, None
        if lowered is None and self._restore_leftover:
            self._restore_leftover = False
            return lambda _: self._restore(game), None

        silent_for = self._clock() - self._silent_since
        holding = not self._speaking and silent_for < self._timing.hold
        if not (self._enabled and (self._speaking or holding)):
            return (self._release, None) if lowered is not None else (None, None)
        if lowered is None:
            if self._tried_stretch == self._stretch:
                return None, None
            self._tried_stretch = self._stretch
            level = self._level
            return lambda _: self._lower(game, level), None
        target = lowered.original * self._level
        if not math.isclose(lowered.current, target, abs_tol=1e-6):
            return lambda current: self._fade_to(current, target), None
        return None, self._timing.hold - silent_for if holding else None

    def _lower(self, game: ProcessInfo, level: float) -> _Lowered | None:
        volume = self._open_volume(game.pid)
        if volume is None:
            logger.info("%s plays no sound to lower right now", game.name)
            return None
        current = volume.get()
        # A record means an earlier run left the game lowered: the current volume is not its own.
        original = self._records.get(game.name)
        if original is None:
            original = current
        self._records.put(game.name, original)
        return self._fade_to(_Lowered(game, volume, original, current), original * level)

    def _fade_to(self, lowered: _Lowered | None, target: float) -> _Lowered | None:
        assert lowered is not None
        seconds = self._timing.fade_down if target < lowered.current else self._timing.fade_up
        self._fade(lowered, target, seconds, interrupted=lambda: False)
        return lowered

    def _release(self, lowered: _Lowered | None) -> _Lowered | None:
        assert lowered is not None
        # Speech starting again stops the fade; the game is then lowered again from where it got to.
        if not self._fade(lowered, lowered.original, self._timing.fade_up, lambda: self._enabled and self._speaking):
            return lowered
        self._records.remove(lowered.game.name)
        return None

    def _forget(self, lowered: _Lowered | None) -> None:
        assert lowered is not None
        logger.info("%s exited while lowered; its volume is restored when it starts again", lowered.game.name)

    def _restore(self, game: ProcessInfo) -> None:
        original = self._records.get(game.name)
        if original is None:
            return
        volume = self._open_volume(game.pid)
        if volume is None:
            return  # Restored when the game is first lowered.
        volume.set(original)
        self._records.remove(game.name)
        logger.info("Restored the volume of %s, left lowered by an earlier run", game.name)

    def _fade(self, lowered: _Lowered, target: float, seconds: float, interrupted: Callable[[], bool]) -> bool:
        """Moves the volume to target in small steps; returns False if interrupted."""
        start = lowered.current
        steps = max(1, round(seconds / self._timing.step)) if self._timing.step > 0 else 1
        for index in range(1, steps + 1):
            if interrupted():
                return False
            self._set(lowered, target if index == steps else start + (target - start) * index / steps)
            if index < steps:
                self._sleep(self._timing.step)
        return True

    def _set(self, lowered: _Lowered, level: float) -> None:
        lowered.volume.set(level)
        lowered.current = level
