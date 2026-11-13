"""Reads and checks request bodies, with the help text a refused request answers with."""

from collections.abc import Callable
from typing import Any

from aiohttp import web

from reflektortts.events import Output
from reflektortts.settings import SettingsChange
from reflektortts.sinks.subtitles import POSITIONS, SIZES
from reflektortts.tts.engine import MAX_RATE, MIN_RATE
from reflektortts.tts.service import NewLine

SETTINGS_HELP = (
    'Send any of "input_language", "output_language" and "voice" (text), "ducking" and "subtitles" (true or '
    'false), "duck_volume" (a number from 0 to 1), "speech_rate" (a number from 0.5 to 2), "new_line" ("wait", '
    '"cut_off" or "speed_up"), "subtitle_size" ("small", "medium" or "large") and "subtitle_position" ("top" or '
    '"bottom"), e.g. {"output_language": "pl"}.'
)


SOURCES_HELP = 'Send {"name": "<source name from the profile’s settings>", "enabled": true or false}.'


OUTPUTS = tuple(output.value for output in Output)


STAGES_HELP = (
    'Send {"key": "<stage key from the profile’s settings>", "output": "text" or "speech", "enabled": true or false}.'
)


PROFILES_HELP = 'Send {"id": "<id from GET /v1/profiles>", "enabled": true or false}.'


INTEGRATION_HELP = 'Send {"enabled": true or false}.'


IMPORT_HELP = 'Send {"id": "<the file name without .json>", "profile": {<the profile>}, "replace": true or false}.'


async def read_object(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def is_fraction(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


def is_rate(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and MIN_RATE <= value <= MAX_RATE


def is_text(value: object) -> bool:
    return isinstance(value, str)


def is_flag(value: object) -> bool:
    return isinstance(value, bool)


SETTING_CHECKS: dict[str, Callable[[object], bool]] = {
    "input_language": is_text,
    "output_language": is_text,
    "voice": is_text,
    "ducking": is_flag,
    "duck_volume": is_fraction,
    "speech_rate": is_rate,
    "new_line": lambda value: value in tuple(NewLine),
    "subtitles": is_flag,
    "subtitle_size": lambda value: value in SIZES,
    "subtitle_position": lambda value: value in POSITIONS,
}


def settings_change(values: dict[str, Any]) -> SettingsChange:
    """A change from settings checked with SETTING_CHECKS."""
    fields = dict(values)
    for field in ("duck_volume", "speech_rate"):
        if field in fields:
            fields[field] = float(fields[field])
    if "new_line" in fields:
        fields["new_line"] = NewLine(fields["new_line"])
    return SettingsChange(**fields)


DOWNLOADS_HELP = 'Send {"id": "<id from GET /v1/downloads>"}.'
