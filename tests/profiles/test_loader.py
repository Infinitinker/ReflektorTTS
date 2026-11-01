import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reflektortts.profiles import loader
from reflektortts.profiles.loader import PluginSchemas, ProfileError, load_profile, load_profiles
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings, StageSettings

REPO_PROFILES = Path(__file__).resolve().parents[2] / "profiles"

VALID: dict[str, Any] = {
    "version": 1,
    "app": {"title": "Test App", "year": 1999},
    "match": {"executables": [{"name": "test.exe"}]},
}
BUILD = "15e3cfedba9a841df67d8194e7249afb493b0e10d6138fb8ebab2c136e543efb"


def write(directory: Path, name: str, data: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def test_valid_profile_loads(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, "test-app-1999.json", VALID))

    assert profile == Profile(
        id="test-app-1999",
        app=App(title="Test App", year=1999),
        match=Match((Executable("test.exe"),)),
    )


def test_builds_are_listed_by_hash_and_the_overlay_is_off_unless_asked_for(tmp_path: Path) -> None:
    data = VALID | {"match": {"executables": [{"name": "test.exe", "sha256": [BUILD]}]}}

    profile = load_profile(write(tmp_path, "app.json", data))

    assert profile.match == Match((Executable("test.exe", (BUILD,)),))
    assert not profile.overlay
    assert load_profile(write(tmp_path, "app.json", data | {"overlay": True})).overlay


def test_the_overlay_needs_the_builds_it_was_tested_with(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match='app.json: "overlay" needs the "sha256" of every executable'):
        load_profile(write(tmp_path, "app.json", VALID | {"overlay": True}))


def test_profiles_shipped_in_the_repo_are_valid() -> None:
    profiles, errors = load_profiles(REPO_PROFILES)

    assert errors == []
    assert "grand-theft-auto-2-1999" in [profile.id for profile in profiles]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"app": {"title": "Test App"}}, "'year' is a required property"),
        ({"match": {"executables": []}}, "$.match.executables"),
        ({"match": {"executables": [{"name": "C:\\Apps\\test.exe"}]}}, "$.match.executables[0].name"),
        ({"match": {"executables": [{"name": "test.exe", "sha256": ["ABC"]}]}}, "$.match.executables[0].sha256[0]"),
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
    with pytest.raises(ProfileError, match="Update ReflektorTTS"):
        load_profile(write(tmp_path, "future.json", VALID | {"version": 99}))


TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["text"],
    "additionalProperties": False,
    "properties": {"text": {"type": "string"}},
}


LIMIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"limit": {"type": "integer"}},
}
SCHEMAS = PluginSchemas(sources={"fixed": TEXT_SCHEMA}, stages={"cut": LIMIT_SCHEMA})


def with_sources(*sources: dict[str, Any]) -> dict[str, Any]:
    return VALID | {"sources": list(sources)}


def test_an_older_profile_is_migrated_to_the_current_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No migration exists before the first release, so a stand-in version 2 renames the title.
    monkeypatch.setattr(loader, "CURRENT_VERSION", 2)
    monkeypatch.setattr(
        loader, "MIGRATIONS", {1: lambda data: data | {"version": 2, "app": data["app"] | {"title": "Renamed"}}}
    )
    monkeypatch.setattr(loader, "_validator", lambda: Draft202012Validator({}))

    profile = load_profile(write(tmp_path, "old.json", VALID), SCHEMAS)

    assert profile.app.title == "Renamed"


def test_sources_are_split_into_core_fields_and_plugin_settings(tmp_path: Path) -> None:
    data = with_sources(
        {"type": "fixed", "name": "first", "text": "hi"},
        {
            "type": "fixed",
            "name": "second",
            "poll_interval_ms": 1000,
            "text": "yo",
            "stages": [{"type": "cut", "limit": 3}, {"type": "cut"}],
        },
    )

    profile = load_profile(write(tmp_path, "app.json", data), SCHEMAS)

    assert profile.sources == (
        SourceSettings(type="fixed", name="first", poll_interval=0.25, settings={"text": "hi"}),
        SourceSettings(
            type="fixed",
            name="second",
            poll_interval=1.0,
            settings={"text": "yo"},
            stages=(StageSettings(type="cut", settings={"limit": 3}), StageSettings(type="cut", settings={})),
        ),
    )


def test_two_sources_with_one_name_are_refused(tmp_path: Path) -> None:
    data = with_sources(
        {"type": "fixed", "name": "subtitles", "text": "a"}, {"type": "fixed", "name": "subtitles", "text": "b"}
    )

    with pytest.raises(ProfileError, match='app.json: two sources are named "subtitles"; give each its own name.'):
        load_profile(write(tmp_path, "app.json", data), SCHEMAS)


def test_unknown_source_type_lists_the_installed_ones(tmp_path: Path) -> None:
    data = with_sources({"type": "ocr", "name": "subtitles"})

    with pytest.raises(ProfileError, match=r'\$\.sources\[0\]: unknown source type "ocr" \(installed: fixed\)'):
        load_profile(write(tmp_path, "app.json", data), SCHEMAS)


def test_unknown_stage_type_is_reported_with_its_position(tmp_path: Path) -> None:
    data = with_sources({"type": "fixed", "name": "first", "text": "hi", "stages": [{"type": "cut"}, {"type": "x"}]})

    with pytest.raises(ProfileError, match=r'\$\.sources\[0\]\.stages\[1\]: unknown stage type "x" \(installed: cut\)'):
        load_profile(write(tmp_path, "app.json", data), SCHEMAS)


def test_plugin_settings_are_validated_against_the_plugin_schema(tmp_path: Path) -> None:
    data = with_sources({"type": "fixed", "name": "first", "text": 5})

    with pytest.raises(ProfileError, match=r"app\.json: \$\.sources\[0\]\.text: 5 is not of type 'string'"):
        load_profile(write(tmp_path, "app.json", data), SCHEMAS)


def test_stage_settings_are_validated_against_the_plugin_schema(tmp_path: Path) -> None:
    data = with_sources({"type": "fixed", "name": "first", "text": "hi", "stages": [{"type": "cut", "limit": "3"}]})

    with pytest.raises(ProfileError, match=r"\$\.sources\[0\]\.stages\[0\]\.limit: '3' is not of type 'integer'"):
        load_profile(write(tmp_path, "app.json", data), SCHEMAS)


def test_broken_profile_does_not_stop_the_others(tmp_path: Path) -> None:
    write(tmp_path, "a-good-1999.json", VALID)
    write(tmp_path, "b-broken.json", "[]")
    write(tmp_path, "notes.txt", "not a profile")

    profiles, errors = load_profiles(tmp_path)

    assert [profile.id for profile in profiles] == ["a-good-1999"]
    assert [str(error) for error in errors] == ["b-broken.json: must contain a JSON object."]
