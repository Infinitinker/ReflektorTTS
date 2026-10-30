"""Per-user settings, stored as JSON in the user's config folder."""

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import platformdirs

from reflektortts.tts.engine import DEFAULT_VOICE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    voice: str = DEFAULT_VOICE
    """Voice as "engine:name", e.g. "windows:Microsoft Adam"."""


def settings_path() -> Path:
    return platformdirs.user_config_path("reflektortts", appauthor=False) / "settings.json"


def load_settings(path: Path) -> Settings:
    """Reads settings; missing ones get defaults. A broken file is reported and replaced by defaults."""
    if not path.is_file():
        return Settings()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.error("Cannot read settings from %s (%s); using defaults.", path, error)
        return Settings()
    if not isinstance(data, dict):
        logger.error("Settings in %s are not a JSON object; using defaults.", path)
        return Settings()
    known = {field.name: data[field.name] for field in fields(Settings) if isinstance(data.get(field.name), str)}
    return Settings(**known)


def save_settings(settings: Settings, path: Path) -> None:
    """Writes settings through a temporary file, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2) + "\n", "utf-8")
    os.replace(temporary, path)
