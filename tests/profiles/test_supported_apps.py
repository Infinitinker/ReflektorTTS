"""SUPPORTED-APPS.md lists exactly the bundled profiles, each with its own medal, tested languages and overlay."""

import re
from pathlib import Path

from reflektortts.languages import LANGUAGES
from reflektortts.profiles.catalog import BUNDLED_DIR, load_catalog
from reflektortts.profiles.model import ANY_LANGUAGE, Profile, Rating

SUPPORTED_APPS = Path(__file__).parents[2] / "SUPPORTED-APPS.md"
MEDALS = {
    Rating.BRONZE: "🥉 Bronze",
    Rating.SILVER: "🥈 Silver",
    Rating.GOLD: "🥇 Gold",
    Rating.PLATINUM: "💎 Platinum",
}
ROW = re.compile(
    r"^\| \[(?P<title>[^\]]+)\]\(#(?P<anchor>[^)]+)\) \| [^|]+ \| (?P<medal>[^|]+) \| (?P<languages>[^|]+) \| [^|]+ "
    r"\| (?P<overlay>[^|]+) \|$",
    re.MULTILINE,
)


def bundled_profiles() -> list[Profile]:
    profiles = [entry.profile for entry in load_catalog(Path("no-such-folder"), BUNDLED_DIR)]
    assert None not in profiles
    return [profile for profile in profiles if profile is not None]


def languages(profile: Profile) -> str:
    """The languages it was tested with, as the table names them, e.g. "English, Polish"."""
    if profile.tested_languages == ANY_LANGUAGE:
        return "Any language"
    return ", ".join(LANGUAGES[code].english_name for code in profile.tested_languages)


def rating(profile: Profile) -> str:
    """Its section's rating, e.g. "💎 Platinum, tested with English and Polish"."""
    assert profile.rating is not None
    if profile.tested_languages == ANY_LANGUAGE:
        return f"{MEDALS[profile.rating]}, tested with any language"
    *others, last = [LANGUAGES[code].english_name for code in profile.tested_languages]
    return f"{MEDALS[profile.rating]}, tested with {' and '.join([', '.join(others), last] if others else [last])}"


def anchor(heading: str) -> str:
    """The link GitHub gives a heading: lowercase, punctuation dropped, spaces as dashes."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def test_the_table_has_a_row_for_each_bundled_profile_and_no_other() -> None:
    rows = {match["title"]: match for match in ROW.finditer(SUPPORTED_APPS.read_text("utf-8"))}

    assert sorted(rows) == sorted(profile.app.title for profile in bundled_profiles())
    for profile in bundled_profiles():
        row = rows[profile.app.title]
        assert profile.rating is not None
        assert row["medal"].strip() == MEDALS[profile.rating]
        assert row["languages"].strip() == languages(profile)
        assert row["overlay"].strip() == ("Yes" if profile.overlay else "No")
        assert row["anchor"] == anchor(profile.app.title)


def test_each_bundled_profile_has_a_section_that_gives_its_medal_and_languages() -> None:
    text = SUPPORTED_APPS.read_text("utf-8")

    for profile in bundled_profiles():
        assert profile.rating is not None
        heading = f"\n## {profile.app.title}\n"
        assert heading in text
        section = text.split(heading, 1)[1].split("\n## ", 1)[0]
        assert f"- **Rating**: {rating(profile)}." in section
