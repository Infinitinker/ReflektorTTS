"""A loaded, validated profile: one app, or another program, whose text is read aloud."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Literal

from reflektortts.glossary import Glossaries


@dataclass(frozen=True)
class App:
    title: str
    year: int


ANY_LANGUAGE: Final = "any"
"""tested_languages of a profile that reads text whatever its language."""


class Rating(StrEnum):
    """How far a profile is tested, as a medal, from the least tested."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


@dataclass(frozen=True)
class Executable:
    name: str
    """The file name, without folders, e.g. "gta2.exe"."""
    sha256: tuple[str, ...] = ()
    """The builds the profile supports, by the SHA-256 of the file (lowercase hex); empty: any
    build with this name."""


@dataclass(frozen=True)
class Match:
    """How to recognize the running program."""

    executables: tuple[Executable, ...]


@dataclass(frozen=True)
class StageSettings:
    """One stage of a source; settings holds the plugin's own, schema-validated fields."""

    type: str
    settings: Mapping[str, Any]
    text: bool = True
    """Whether the stage starts on for the text shown (subtitles, the API's events)."""
    speech: bool = True
    """Whether the stage starts on for what is spoken."""


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
    app: App
    match: Match
    sources: tuple[SourceSettings, ...] = field(default=())
    overlay: bool = False
    """Whether the overlay is loaded into the program; only into builds listed by hash."""
    glossary: Glossaries = field(default_factory=dict)
    """Terms of the app that translation and speech treat specially, by input language; given to
    every stage."""
    rating: Rating | None = None
    """How far the profile is tested; None if it is not rated."""
    tested_languages: tuple[str, ...] | Literal["any"] = ()
    """The languages the profile was tested with: the app's own, and those its lines were translated
    into and spoken in; ANY_LANGUAGE if it reads text whatever its language; empty if it does not
    say. Any other language can still be chosen: these are the ones tried."""
