"""A loaded, validated game profile."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Game:
    title: str
    year: int


@dataclass(frozen=True)
class Match:
    """How to recognize the running game."""

    processes: tuple[str, ...]


@dataclass(frozen=True)
class Profile:
    id: str
    """The file name without .json, e.g. "grand-theft-auto-2-1999"."""
    game: Game
    match: Match
