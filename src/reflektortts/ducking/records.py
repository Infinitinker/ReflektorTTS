"""Remembers apps' original volumes while they are lowered, so a crash cannot leave an app quiet.

Windows keeps each app's mixer volume between runs: an app still lowered when ReflektorTTS
stopped would start quiet next time. The record lets its volume be put back.
"""

import json
import logging
import os
from pathlib import Path

from reflektortts.user_dirs import state_dir

logger = logging.getLogger(__name__)


def records_path() -> Path:
    return state_dir() / "lowered-apps.json"


class DuckRecords:
    """Original volumes by process name, in a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, name: str) -> float | None:
        return self._read().get(name.lower())

    def put(self, name: str, level: float) -> None:
        self._write(self._read() | {name.lower(): level})

    def remove(self, name: str) -> None:
        records = self._read()
        if records.pop(name.lower(), None) is not None:
            self._write(records)

    def _read(self) -> dict[str, float]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.error("Cannot read %s (%s); app volumes it held are lost.", self._path, error)
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            key: float(value)
            for key, value in data.items()
            if isinstance(value, int | float) and not isinstance(value, bool)
        }

    def _write(self, records: dict[str, float]) -> None:
        if not records:
            self._path.unlink(missing_ok=True)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, indent=2) + "\n", "utf-8")
        os.replace(temporary, self._path)
