"""What the desktop app shows of the profiles, from GET /v1/profiles."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Any

ORIGINS = {"bundled": "Bundled", "custom": "Your own", "override": "Your own (replaces bundled)"}
STATES = {
    "reading": "Reading",
    "not_running": "Not running",
    "unsupported": "Unsupported version",
    "not_set_up": "Not set up",
    "disabled": "Disabled",
    "not_used": "Not used",
    "clash": "Clash",
    "broken": "Broken",
}
RATINGS = {
    "bronze": ("Bronze", "Some of the app’s texts are read, tried only briefly, so others may be missed."),
    "silver": ("Silver", "The main texts are read, tested in the first part of the app."),
    "gold": ("Gold", "The main texts are read, tested through most of the app."),
    "platinum": ("Platinum", "Every text the app shows is read, tested through all of it."),
}
"""Each medal's name and what it says about a profile, by the medal's name in the API."""
NOT_RATED = ("Not rated", "Its author did not say how far it is tested.")
ANY_LANGUAGE = "any"
"""The API's tested_languages for a profile that reads text whatever its language."""
ANY_LANGUAGE_TEXT = "Any language"
SHOWN_CODES = 3
"""How many tested languages the list shows by code before counting the rest."""
IN_USE = ("reading", "not_running", "unsupported")
"""States of a profile that is used, whatever its app is doing."""


@dataclass(frozen=True)
class ExecutableItem:
    name: str
    sha256: tuple[str, ...]
    """Empty: any build."""


@dataclass(frozen=True)
class SourceItem:
    name: str
    type: str
    stages: tuple[str, ...]


@dataclass(frozen=True)
class ProfileItem:
    id: str
    title: str | None
    """None for a broken file."""
    year: int | None
    origin: str
    """As the API names it: "bundled", "custom" or "override"."""
    state: str
    """As the API names it, e.g. "reading" or "clash"."""
    reason: str | None
    file: str
    overlay: bool | None
    rating: str | None
    """As the API names it, e.g. "gold"; None if not rated, or for a broken file."""
    tested_languages: tuple[str, ...] | str
    """Codes of the languages it was tested with, or ANY_LANGUAGE; empty if not said."""
    glossary_languages: tuple[str, ...]
    """The input languages its glossary has terms for."""
    pronunciation_languages: tuple[str, ...]
    """The output languages its glossary says how to pronounce terms in."""
    speech_rules: tuple[tuple[str, tuple[str, ...]], ...]
    """What its stages do only for some output languages, each with those languages' codes, e.g.
    ("Numbers, dates and units", ("en", "pl"))."""
    executables: tuple[ExecutableItem, ...]
    sources: tuple[SourceItem, ...]


def parse_profiles(data: Mapping[str, Any]) -> list[ProfileItem]:
    return [
        ProfileItem(
            id=profile["id"],
            title=profile["title"],
            year=profile["year"],
            origin=profile["origin"],
            state=profile["state"],
            reason=profile["reason"],
            file=profile["file"],
            overlay=profile["overlay"],
            rating=profile["rating"],
            tested_languages=_tested(profile["tested_languages"]),
            glossary_languages=tuple(profile["glossary_languages"]),
            pronunciation_languages=tuple(profile["pronunciation_languages"]),
            speech_rules=tuple((rule["name"], tuple(rule["languages"])) for rule in profile["speech_rules"]),
            executables=tuple(
                ExecutableItem(executable["name"], tuple(executable["sha256"])) for executable in profile["executables"]
            ),
            sources=tuple(
                SourceItem(source["name"], source["type"], tuple(source["stages"])) for source in profile["sources"]
            ),
        )
        for profile in data["profiles"]
    ]


def _tested(languages: list[str] | str) -> tuple[str, ...] | str:
    return ANY_LANGUAGE if languages == ANY_LANGUAGE else tuple(languages)


def file_name(item: ProfileItem) -> str:
    return PureWindowsPath(item.file).name


def name_text(item: ProfileItem) -> str:
    """The profile's name, e.g. "Grand Theft Auto 2 (1999)", or a broken one's file name."""
    return f"{item.title} ({item.year})" if item.title is not None else file_name(item)


def overlay_text(item: ProfileItem) -> str:
    return "" if item.overlay is None else ("Yes" if item.overlay else "No")


def rating_text(item: ProfileItem) -> tuple[str, str]:
    """The medal's name and what it means, e.g. ("Gold", "The main texts are read, ..."); empty
    for a broken file, which has none."""
    if item.title is None:
        return "", ""
    return RATINGS[item.rating] if item.rating is not None else NOT_RATED


def languages_column_text(item: ProfileItem) -> str:
    """The languages it was tested with, for the list: their codes, the first few and how many
    more, e.g. "EN, PL, DE +6"; "Any language"; or nothing if it does not say."""
    if item.tested_languages == ANY_LANGUAGE:
        return ANY_LANGUAGE_TEXT
    codes = ", ".join(code.upper() for code in item.tested_languages[:SHOWN_CODES])
    more = len(item.tested_languages) - SHOWN_CODES
    return f"{codes} +{more}" if more > 0 else codes


def summary_text(items: Sequence[ProfileItem]) -> str:
    used = sum(item.state in IN_USE for item in items)
    return f"Profiles: {len(items)}, used: {used}"


def details_text(item: ProfileItem, language_name: Callable[[str], str]) -> str:
    """The reason it is not used, if any, what its medal means, the languages it was tested with,
    those its glossary covers and those its stages' speech rules cover, then its executables and
    sources. language_name names a language by its code."""
    lines = [item.reason, ""] if item.reason else []
    medal, meaning = rating_text(item)
    if medal:
        lines.append(f"{medal}: {meaning}")
        lines += [
            f"{label}: {names}"
            for label, names in (
                ("Tested languages", _names(item.tested_languages, language_name)),
                ("Glossary", _names(item.glossary_languages, language_name)),
                ("Pronunciation", _names(item.pronunciation_languages, language_name)),
                *((rule, _names(languages, language_name)) for rule, languages in item.speech_rules),
            )
            if names
        ]
        lines.append("")
    for executable in item.executables:
        builds = ", ".join(executable.sha256) if executable.sha256 else "any version"
        lines.append(f"{executable.name}: {builds}")
    for source in item.sources:
        stages = ", ".join(source.stages) if source.stages else "no stages"
        lines.append(f"{source.name} ({source.type}): {stages}")
    return "\n".join(lines).strip()


def _names(languages: tuple[str, ...] | str, language_name: Callable[[str], str]) -> str:
    if languages == ANY_LANGUAGE:
        return ANY_LANGUAGE_TEXT
    return ", ".join(language_name(code) for code in languages)
