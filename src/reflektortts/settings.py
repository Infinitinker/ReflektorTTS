"""Per-user settings, stored as JSON in the settings folder of the user's config folder.

Each app has its own file, profiles/<profile ID>.json, with everything the user set in the panel
for it; an app without one has the defaults. shared.json holds the voice last chosen for each
language, in any app. On the first run neither exists.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from reflektortts.ducking.ducker import DEFAULT_LEVEL
from reflektortts.events import Output
from reflektortts.languages import DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE, LANGUAGES
from reflektortts.sinks.subtitles import DEFAULT_POSITION, DEFAULT_SIZE, POSITIONS, SIZES
from reflektortts.tts.engine import DEFAULT_VOICE, MAX_RATE, MIN_RATE

logger = logging.getLogger(__name__)

SETTINGS_FOLDER = "settings"
SHARED_FILE = "shared.json"
PROFILES_FOLDER = "profiles"


@dataclass(frozen=True)
class ProfileSettings:
    """Everything the user sets in the panel, for one app."""

    voice: str = DEFAULT_VOICE
    """Voice as "engine:name", e.g. "windows:Microsoft Adam"."""
    input_language: str = DEFAULT_INPUT_LANGUAGE
    """The language of the app's text (ISO 639-1)."""
    output_language: str = DEFAULT_OUTPUT_LANGUAGE
    """The language lines are prepared, spoken and shown in (ISO 639-1)."""
    ducking: bool = True
    """Whether the app's sound is lowered while lines are spoken."""
    duck_volume: float = DEFAULT_LEVEL
    """The app's volume while lines are spoken, as a fraction of its own volume (0.0 to 1.0)."""
    speech_rate: float = 1.0
    """How fast lines are spoken, as a multiple of the voice's own pace (MIN_RATE to MAX_RATE)."""
    cut_off_lines: bool = False
    """Whether a new line cuts off the one being spoken; otherwise lines wait their turn."""
    subtitles: bool = False
    """Whether lines are shown as subtitles over the app."""
    subtitle_size: str = DEFAULT_SIZE
    """One of SIZES."""
    subtitle_position: str = DEFAULT_POSITION
    """One of POSITIONS: where on the screen subtitles are shown."""
    disabled_sources: tuple[str, ...] = ()
    """Names of the sources the user switched off."""
    stage_switches: dict[str, dict[Output, bool]] = field(default_factory=dict)
    """How the user switched stages, by key and output, e.g. {"subtitles/3:normalize": {"text": True}};
    a stage is otherwise on where its profile starts it."""


@dataclass(frozen=True)
class SharedSettings:
    """Settings for every app."""

    voices_by_language: dict[str, str] = field(default_factory=dict)
    """The voice last chosen for each output language, e.g. {"pl": "windows:Microsoft Adam"}."""
    disabled_profiles: tuple[str, ...] = ()
    """IDs of the profiles the user disabled."""


def load_shared(directory: Path) -> SharedSettings:
    """Reads shared.json; missing or invalid settings get defaults."""
    data = _read(directory / SETTINGS_FOLDER / SHARED_FILE)
    return SharedSettings(
        voices_by_language=_text_map(data.get("voices_by_language")),
        disabled_profiles=_texts(data.get("disabled_profiles")),
    )


def save_shared(settings: SharedSettings, directory: Path) -> None:
    _write(directory / SETTINGS_FOLDER / SHARED_FILE, asdict(settings))


def load_profile_settings(directory: Path, profile_id: str) -> ProfileSettings:
    """An app's settings; missing or invalid ones get defaults."""
    return _profile_settings(_read(_profile_settings_path(directory, profile_id)))


def save_profile_settings(settings: ProfileSettings, directory: Path, profile_id: str) -> None:
    _write(_profile_settings_path(directory, profile_id), asdict(settings))


def _profile_settings_path(directory: Path, profile_id: str) -> Path:
    return directory / SETTINGS_FOLDER / PROFILES_FOLDER / f"{profile_id}.json"


def _read(path: Path) -> dict[str, Any]:
    """A settings file's fields; none if it is missing, and a broken file is reported."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.error("Cannot read settings from %s (%s); using defaults.", path, error)
        return {}
    if not isinstance(data, dict):
        logger.error("Settings in %s are not a JSON object; using defaults.", path)
        return {}
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    """Writes through a temporary file, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    os.replace(temporary, path)


def _profile_settings(data: dict[str, Any]) -> ProfileSettings:
    defaults = ProfileSettings()
    return ProfileSettings(
        voice=_text(data, "voice", defaults.voice),
        # Unsupported languages, such as a leftover "auto", become the default.
        input_language=_choice(data, "input_language", tuple(LANGUAGES), defaults.input_language),
        output_language=_choice(data, "output_language", tuple(LANGUAGES), defaults.output_language),
        ducking=_flag(data, "ducking", defaults.ducking),
        duck_volume=_number(data, "duck_volume", defaults.duck_volume, 0.0, 1.0),
        speech_rate=_number(data, "speech_rate", defaults.speech_rate, MIN_RATE, MAX_RATE),
        cut_off_lines=_flag(data, "cut_off_lines", defaults.cut_off_lines),
        subtitles=_flag(data, "subtitles", defaults.subtitles),
        subtitle_size=_choice(data, "subtitle_size", SIZES, defaults.subtitle_size),
        subtitle_position=_choice(data, "subtitle_position", POSITIONS, defaults.subtitle_position),
        disabled_sources=_texts(data.get("disabled_sources")),
        stage_switches=_stage_switches(data.get("stage_switches")),
    )


def _text(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def _flag(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key)
    return value if isinstance(value, bool) else default


def _number(data: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    value = data.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high:
        return float(value)
    return default


def _choice(data: dict[str, Any], key: str, choices: tuple[str, ...], default: str) -> str:
    value = data.get(key)
    return value if value in choices else default


def _stage_switches(value: object) -> dict[str, dict[Output, bool]]:
    if not isinstance(value, dict):
        return {}
    switches = {}
    for key, outputs in value.items():
        if isinstance(outputs, dict):
            chosen = {Output(output): on for output, on in outputs.items() if output in Output and isinstance(on, bool)}
            if chosen:
                switches[key] = chosen
    return switches


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _text_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)}
