import json
from pathlib import Path
from typing import Any

import pytest

from reflektortts.profiles.loader import ProfileError, load_profile, load_profiles
from reflektortts.profiles.model import Game, Match, Profile

REPO_PROFILES = Path(__file__).resolve().parents[3] / "profiles"

VALID: dict[str, Any] = {
    "version": 1,
    "game": {"title": "Test Game", "year": 1999},
    "match": {"process": ["test.exe"]},
}


def write(directory: Path, name: str, data: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def test_valid_profile_loads(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, "test-game-1999.json", VALID))

    assert profile == Profile(
        id="test-game-1999",
        game=Game(title="Test Game", year=1999),
        match=Match(processes=("test.exe",)),
    )


def test_profiles_shipped_in_the_repo_are_valid() -> None:
    profiles, errors = load_profiles(REPO_PROFILES)

    assert errors == []
    assert "grand-theft-auto-2-1999" in [profile.id for profile in profiles]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"game": {"title": "Test Game"}}, "'year' is a required property"),
        ({"match": {"process": []}}, "$.match.process"),
        ({"match": {"process": ["C:\\Games\\test.exe"]}}, "$.match.process[0]"),
        ({"extra": True}, "Additional properties are not allowed"),
    ],
)
def test_invalid_profile_names_file_and_problem(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    with pytest.raises(ProfileError) as raised:
        load_profile(write(tmp_path, "broken.json", VALID | change))

    assert str(raised.value).startswith("broken.json: ")
    assert message in str(raised.value)


def test_invalid_json_reports_the_position(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"broken\.json: not valid JSON \(line 1, column 2\)"):
        load_profile(write(tmp_path, "broken.json", "{oops"))


@pytest.mark.parametrize("version", ["1", None, True])
def test_version_must_be_a_number(tmp_path: Path, version: object) -> None:
    with pytest.raises(ProfileError, match="whole number"):
        load_profile(write(tmp_path, "broken.json", VALID | {"version": version}))


def test_profile_from_a_newer_app_asks_to_update(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="Update the app"):
        load_profile(write(tmp_path, "future.json", VALID | {"version": 99}))


def test_broken_profile_does_not_stop_the_others(tmp_path: Path) -> None:
    write(tmp_path, "a-good-1999.json", VALID)
    write(tmp_path, "b-broken.json", "[]")
    write(tmp_path, "notes.txt", "not a profile")

    profiles, errors = load_profiles(tmp_path)

    assert [profile.id for profile in profiles] == ["a-good-1999"]
    assert [str(error) for error in errors] == ["b-broken.json: must contain a JSON object."]
