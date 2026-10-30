"""A loaded, validated game profile."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Game:
    title: str
    year: int


@dataclass(frozen=True)
class Match:
    """How to recognize the running game."""

    processes: tuple[str, ...]


@dataclass(frozen=True)
class StageSettings:
    """One stage of a source; settings holds the plugin's own, schema-validated fields."""

    type: str
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class SourceSettings:
    """One source in a profile. settings holds the plugin's own fields, already validated
    against its schema; the plugin turns them into its own types."""

    type: str
    name: str
    poll_interval: float
    """Seconds between reads."""
    settings: Mapping[str, Any]
    stages: tuple[StageSettings, ...] = field(default=())
    """Applied in order to this source's text."""


@dataclass(frozen=True)
class Profile:
    id: str
    """The file name without .json, e.g. "grand-theft-auto-2-1999"."""
    game: Game
    match: Match
    sources: tuple[SourceSettings, ...] = field(default=())
