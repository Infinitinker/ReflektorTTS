"""Loading profile files: parsing, migrating to the current version, and checking sources, stages and glossaries."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reflektortts.glossary import GlossaryTerm
from reflektortts.profiles import loader
from reflektortts.profiles.loader import PluginSchemas, ProfileError, load_profile
from reflektortts.profiles.model import App, Executable, Match, Profile, Rating, SourceSettings, StageSettings

VALID: dict[str, Any] = {
    "version": 2,
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


def test_a_profile_is_rated_with_a_medal_or_not_at_all(tmp_path: Path) -> None:
    assert load_profile(write(tmp_path, "app.json", VALID)).rating is None
    assert load_profile(write(tmp_path, "app.json", VALID | {"rating": "silver"})).rating == Rating.SILVER
    with pytest.raises(ProfileError, match=r"app.json: .*\$.rating"):
        load_profile(write(tmp_path, "app.json", VALID | {"rating": "wood"}))


def test_a_profile_says_which_app_languages_it_was_tested_in_or_that_it_reads_any(tmp_path: Path) -> None:
    assert load_profile(write(tmp_path, "app.json", VALID)).tested_languages == ()
    tested = VALID | {"tested_languages": ["en", "pl"]}
    assert load_profile(write(tmp_path, "app.json", tested)).tested_languages == ("en", "pl")
    assert load_profile(write(tmp_path, "app.json", VALID | {"tested_languages": "any"})).tested_languages == "any"


@pytest.mark.parametrize("languages", [[], ["en", "en"], ["EN"], "all"])
def test_tested_languages_that_cannot_be_used_are_refused(tmp_path: Path, languages: object) -> None:
    with pytest.raises(ProfileError, match=r"app.json: .*\$.tested_languages"):
        load_profile(write(tmp_path, "app.json", VALID | {"tested_languages": languages}))


def test_a_tested_language_not_known_by_that_code_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r'app.json: \$.tested_languages\[1\]: There is no language "xx"'):
        load_profile(write(tmp_path, "app.json", VALID | {"tested_languages": ["en", "xx"]}))


def test_the_overlay_needs_the_builds_it_was_tested_with(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match='app.json: "overlay" needs the "sha256" of every executable'):
        load_profile(write(tmp_path, "app.json", VALID | {"overlay": True}))


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


def test_invalid_json_says_what_is_wrong_and_where(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"broken\.json: not valid JSON: Expecting property .*\(line 1, column 2\)"):
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
    monkeypatch.setattr(loader, "CURRENT_VERSION", 3)
    monkeypatch.setattr(
        loader,
        "MIGRATIONS",
        loader.MIGRATIONS | {2: lambda data: data | {"version": 3, "app": data["app"] | {"title": "Renamed"}}},
    )
    monkeypatch.setattr(loader, "_validator", lambda: Draft202012Validator({}))

    profile = load_profile(write(tmp_path, "old.json", VALID | {"version": 1}), SCHEMAS)

    assert profile.app.title == "Renamed"


def test_a_version_1_profile_does_not_say_which_languages_it_was_tested_in(tmp_path: Path) -> None:
    profile = load_profile(write(tmp_path, "app.json", VALID | {"version": 1, "rating": "gold"}))

    assert (profile.rating, profile.tested_languages) == (Rating.GOLD, ())


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


def test_a_stage_says_where_it_starts_on(tmp_path: Path) -> None:
    data = with_sources(
        {"type": "fixed", "name": "first", "text": "hi", "stages": [{"type": "cut", "text": False}, {"type": "cut"}]}
    )

    [source] = load_profile(write(tmp_path, "game.json", data), SCHEMAS).sources

    assert [(stage.text, stage.speech, stage.settings) for stage in source.stages] == [
        (False, True, {}),
        (True, True, {}),
    ]


def test_where_a_stage_starts_on_must_be_true_or_false(tmp_path: Path) -> None:
    data = with_sources({"type": "fixed", "name": "first", "text": "hi", "stages": [{"type": "cut", "speech": "no"}]})

    with pytest.raises(ProfileError, match=r"stages\[0\]\.speech"):
        load_profile(write(tmp_path, "game.json", data), SCHEMAS)


def test_the_glossary_says_what_to_do_with_each_term(tmp_path: Path) -> None:
    glossary = [
        {"term": "Sweet", "keep": True},
        {"term": "Kendl", "keep": True, "female": True, "pronounce": {"pl": "Kendal"}},
        {"term": "hood", "means": "neighborhood"},
        {"term": "Carl", "pronounce": {"pl": "Karl"}},
    ]

    profile = load_profile(write(tmp_path, "app.json", VALID | {"glossary": {"en": glossary}}))

    assert profile.glossary == {
        "en": (
            GlossaryTerm("Sweet", keep=True),
            GlossaryTerm("Kendl", keep=True, female=True, pronounce={"pl": "Kendal"}),
            GlossaryTerm("hood", means="neighborhood"),
            GlossaryTerm("Carl", pronounce={"pl": "Karl"}),
        )
    }


def test_a_term_can_be_spelled_several_ways(tmp_path: Path) -> None:
    glossary = [{"term": ["Big Smoke", "Big smoke"], "keep": True}, {"term": ["hood"], "means": "turf"}]

    profile = load_profile(write(tmp_path, "app.json", VALID | {"glossary": {"en": glossary}}))

    assert profile.glossary == {
        "en": (
            GlossaryTerm("Big Smoke", keep=True, other_spellings=("Big smoke",)),
            GlossaryTerm("hood", means="turf"),
        )
    }


def test_glossaries_are_by_input_language(tmp_path: Path) -> None:
    glossary = {"en": [{"term": "hood", "means": "turf"}], "de": [{"term": "Kiez", "means": "Viertel"}]}

    profile = load_profile(write(tmp_path, "app.json", VALID | {"glossary": glossary}))

    assert profile.glossary == {
        "en": (GlossaryTerm("hood", means="turf"),),
        "de": (GlossaryTerm("Kiez", means="Viertel"),),
    }
    with pytest.raises(ProfileError, match=r"\$\.glossary"):
        load_profile(write(tmp_path, "app.json", VALID | {"glossary": {"english": []}}))


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([{"term": "Sweet"}], 'glossary.en[0] ("Sweet"): says nothing to do with the term'),
        ([{"term": "Sweet", "keep": False}], 'glossary.en[0] ("Sweet"): says nothing to do with the term'),
        ([{"term": "hood", "keep": True, "means": "area"}], "a term is either kept or given a meaning"),
        ([{"term": "Kendl", "female": True, "pronounce": {"pl": "Kendal"}}], '"female" applies only to a kept term'),
        (
            [{"term": "CJ", "keep": True}, {"term": "CJ", "pronounce": {"pl": "Sidżej"}}],
            'glossary.en[1] ("CJ"): "CJ" is in the glossary twice',
        ),
        ([{"term": "Carl", "pronounce": {"polish": "Karl"}}], "$.glossary.en[0].pronounce"),
        (
            [{"term": ["hood", "'hood", "hood"], "means": "turf"}],
            """glossary.en[0] ("hood"): "hood" is in the glossary twice""",
        ),
        (
            [{"term": "Big Smoke", "keep": True}, {"term": ["Smoke", "Big Smoke"], "keep": True}],
            '"Big Smoke" is in the glossary twice',
        ),
        ([{"term": [], "keep": True}], "$.glossary.en[0].term"),
        ([{"term": "", "keep": True}], "$.glossary.en[0].term"),
        ([{"term": "Oslo", "pronounce": {"no": "Uslo"}}], 'Use "nb" (Norwegian Bokmål) instead of "no"'),
        ([{"term": "Carl", "pronounce": {"xx": "Karl"}}], 'There is no language "xx"'),
    ],
)
def test_a_glossary_entry_that_cannot_be_used_is_refused(tmp_path: Path, entries: list[Any], message: str) -> None:
    with pytest.raises(ProfileError) as raised:
        load_profile(write(tmp_path, "app.json", VALID | {"glossary": {"en": entries}}))

    assert message in str(raised.value)


def test_a_profile_saved_with_a_byte_order_mark_loads(tmp_path: Path) -> None:
    path = tmp_path / "test-app-1999.json"
    path.write_text(json.dumps(VALID), encoding="utf-8-sig")

    assert load_profile(path).app == App(title="Test App", year=1999)


def test_a_profile_not_saved_as_utf8_is_refused_in_user_terms(tmp_path: Path) -> None:
    path = tmp_path / "app.json"
    path.write_text(json.dumps(VALID | {"app": {"title": "Paweł", "year": 1999}}, ensure_ascii=False), "cp1250")

    with pytest.raises(ProfileError, match="app.json: not saved as UTF-8"):
        load_profile(path)


def test_a_profile_nested_too_deeply_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="app.json: nested too deeply"):
        load_profile(write(tmp_path, "app.json", "[" * 100_000 + "]" * 100_000))


@pytest.mark.parametrize("version", [0, -1])
def test_a_version_below_1_is_refused(tmp_path: Path, version: int) -> None:
    with pytest.raises(ProfileError, match='app.json: "version" must be from 1 to 2'):
        load_profile(write(tmp_path, "app.json", VALID | {"version": version}))


def test_a_profile_may_name_its_schema_for_editors(tmp_path: Path) -> None:
    schema = json.loads(Path(loader.__file__).with_name("profile.schema.json").read_text("utf-8"))

    profile = load_profile(write(tmp_path, "test-app-1999.json", {"$schema": schema["$id"]} | VALID))

    assert profile.app == App(title="Test App", year=1999)


BUILT_SCHEMAS = PluginSchemas(
    sources={"built": {"type": "object"}},
    stages={},
    source_builds={"built": lambda settings: settings["builds"]},
)
BUILT_MATCH = {"match": {"executables": [{"name": "test.exe", "sha256": [BUILD]}]}}


def test_a_source_for_a_build_the_profile_does_not_list_is_refused(tmp_path: Path) -> None:
    data = with_sources({"type": "built", "name": "subtitles", "builds": [BUILD.upper(), "ab" * 32]}) | BUILT_MATCH

    with pytest.raises(
        ProfileError,
        match=rf'app\.json: \$\.sources\[0\] \("subtitles"\) is set up for the build {"ab" * 32}, which "match" ',
    ):
        load_profile(write(tmp_path, "app.json", data), BUILT_SCHEMAS)


def test_a_source_may_be_for_any_build_when_the_profile_lists_none(tmp_path: Path) -> None:
    data = with_sources({"type": "built", "name": "subtitles", "builds": ["ab" * 32]})

    assert load_profile(write(tmp_path, "app.json", data), BUILT_SCHEMAS).sources[0].name == "subtitles"


def test_a_source_whose_plugin_fails_to_tell_its_builds_is_refused(tmp_path: Path) -> None:
    data = with_sources({"type": "built", "name": "subtitles"}) | BUILT_MATCH

    with pytest.raises(
        ProfileError,
        match=r'app\.json: \$\.sources\[0\] \("subtitles"\): the built source plugin cannot tell which builds',
    ):
        load_profile(write(tmp_path, "app.json", data), BUILT_SCHEMAS)


def test_a_source_whose_plugin_tells_builds_that_are_not_strings_is_refused(tmp_path: Path) -> None:
    data = with_sources({"type": "built", "name": "subtitles", "builds": [None]}) | BUILT_MATCH

    with pytest.raises(ProfileError, match="cannot tell which builds it is for"):
        load_profile(write(tmp_path, "app.json", data), BUILT_SCHEMAS)


def test_a_glossary_in_a_language_not_known_by_that_code_is_refused(tmp_path: Path) -> None:
    glossary = {"no": [{"term": "Oslo", "keep": True}]}

    with pytest.raises(ProfileError, match=r'\$\.glossary\.no: Use "nb"'):
        load_profile(write(tmp_path, "app.json", VALID | {"glossary": glossary}))
