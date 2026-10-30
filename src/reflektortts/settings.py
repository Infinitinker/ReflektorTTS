"""Per-user settings, stored as JSON in the user's config folder."""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

from reflektortts.languages import AUTO, DEFAULT_SPEECH_LANGUAGE
from reflektortts.tts.engine import DEFAULT_VOICE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    voice: str = DEFAULT_VOICE
    """Voice as "engine:name", e.g. "windows:Microsoft Adam"."""
    game_language: str = AUTO
    """The language of the game's text (ISO 639-1), or "auto"."""
    speech_language: str = DEFAULT_SPEECH_LANGUAGE
    """The language lines are prepared and spoken in (ISO 639-1)."""
    voices_by_language: dict[str, str] = field(default_factory=dict)
    """The voice last chosen for each speech language, e.g. {"pl": "windows:Microsoft Adam"}."""
    disabled_stages: dict[str, list[str]] = field(default_factory=dict)
    """Stages switched off by the player, by profile ID: {"grand-theft-auto-2-1999": ["messages/2:normalize"]}."""


def settings_path() -> Path:
    return platformdirs.user_config_path("reflektortts", appauthor=False) / "settings.json"


def _text(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def _text_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)}


def _list_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        key: [item for item in items if isinstance(item, str)]
        for key, items in value.items()
        if isinstance(key, str) and isinstance(items, list)
    }


def load_settings(path: Path) -> Settings:
    """Reads settings; missing or invalid ones get defaults. A broken file is reported and replaced by defaults."""
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
    defaults = Settings()
    # "language" was the speech language before game and speech languages were split.
    speech_language = _text(data, "speech_language", _text(data, "language", defaults.speech_language))
    return Settings(
        voice=_text(data, "voice", defaults.voice),
        game_language=_text(data, "game_language", defaults.game_language),
        speech_language=speech_language,
        voices_by_language=_text_map(data.get("voices_by_language")),
        disabled_stages=_list_map(data.get("disabled_stages")),
    )


def save_settings(settings: Settings, path: Path) -> None:
    """Writes settings through a temporary file, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2) + "\n", "utf-8")
    os.replace(temporary, path)
