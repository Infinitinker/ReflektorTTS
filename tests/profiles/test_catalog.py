"""The profile catalog: the bundled profiles and the user's own, which of them are used, and adding or replacing one."""

import json
from pathlib import Path
from typing import Any

import pytest

from reflektortts.profiles.catalog import (
    BUNDLED_DIR,
    Origin,
    ProfileChangeError,
    ProfileExistsError,
    ProfileStore,
    Standing,
    choose,
    load_catalog,
)
from reflektortts.profiles.loader import PluginSchemas, ProfileError

SCHEMAS = PluginSchemas(sources={}, stages={})
STEAM = "15e3cfedba9a841df67d8194e7249afb493b0e10d6138fb8ebab2c136e543efb"
RETAIL = "420af867036b1a66ef94c54b8db2e7e654da359031987c6602bcfa74972e089f"


def profile(title: str, executable: str = "app.exe", *builds: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": executable} | ({"sha256": list(builds)} if builds else {})
    return {"version": 1, "app": {"title": title, "year": 2000}, "match": {"executables": [entry]}}


def write(directory: Path, profile_id: str, data: object) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data)
    (directory / f"{profile_id}.json").write_text(text, encoding="utf-8")


def standings(tmp_path: Path, disabled: tuple[str, ...] = ()) -> dict[str, tuple[Standing, str | None]]:
    catalog = load_catalog(tmp_path / "user", tmp_path / "bundled", SCHEMAS)
    return {choice.entry.id: (choice.standing, choice.reason) for choice in choose(catalog, disabled)}


def test_the_bundled_profiles_are_valid_and_do_not_clash() -> None:
    choices = choose(load_catalog(Path("no-such-folder"), BUNDLED_DIR), ())

    assert [choice.entry.id for choice in choices if choice.standing == Standing.USED] == [
        "grand-theft-auto-2-1999",
        "grand-theft-auto-iii-2001",
        "grand-theft-auto-san-andreas-2004",
        "grand-theft-auto-vice-city-2002",
        "mad-max-2015",
        "vlc-media-player-2001",
    ]


def test_every_bundled_profile_is_rated() -> None:
    catalog = load_catalog(Path("no-such-folder"), BUNDLED_DIR)
    unrated = [entry.id for entry in catalog if entry.profile is None or entry.profile.rating is None]

    assert unrated == []


def test_every_bundled_profile_says_which_languages_it_was_tested_in() -> None:
    catalog = load_catalog(Path("no-such-folder"), BUNDLED_DIR)
    unsaid = [entry.id for entry in catalog if entry.profile is None or not entry.profile.tested_languages]

    assert unsaid == []


def test_a_user_profile_with_a_bundled_id_replaces_it_even_when_broken(tmp_path: Path) -> None:
    write(tmp_path / "bundled", "game-2000", profile("Bundled"))
    write(tmp_path / "bundled", "other-2000", profile("Other", "other.exe"))
    write(tmp_path / "user", "game-2000", "[]")
    write(tmp_path / "user", "mine-2000", profile("Mine", "mine.exe"))

    catalog = load_catalog(tmp_path / "user", tmp_path / "bundled", SCHEMAS)

    assert [(entry.id, entry.origin, entry.profile is None) for entry in catalog] == [
        ("game-2000", Origin.OVERRIDE, True),
        ("mine-2000", Origin.CUSTOM, False),
        ("other-2000", Origin.BUNDLED, False),
    ]
    assert catalog[0].error == "game-2000.json: must contain a JSON object."


def test_the_users_own_profile_is_used_instead_of_a_bundled_one_for_the_same_app(tmp_path: Path) -> None:
    write(tmp_path / "bundled", "game-2000", profile("Game", "game.exe", STEAM))
    write(tmp_path / "user", "my-game-2000", profile("My game", "GAME.EXE"))

    assert standings(tmp_path) == {
        "game-2000": (Standing.NOT_USED, "My game (my-game-2000.json) is used instead: both match game.exe."),
        "my-game-2000": (Standing.USED, None),
    }


def test_two_of_the_users_profiles_for_the_same_build_clash_until_one_is_disabled(tmp_path: Path) -> None:
    write(tmp_path / "user", "a-2000", profile("A", "game.exe", STEAM))
    write(tmp_path / "user", "b-2000", profile("B", "game.exe", STEAM, RETAIL))

    assert standings(tmp_path) == {
        "a-2000": (Standing.CLASH, "Clashes with B (b-2000.json): both match game.exe. Disable one."),
        "b-2000": (Standing.CLASH, "Clashes with A (a-2000.json): both match game.exe. Disable one."),
    }
    assert standings(tmp_path, disabled=("b-2000",)) == {
        "a-2000": (Standing.USED, None),
        "b-2000": (Standing.DISABLED, None),
    }


def test_profiles_for_different_builds_of_one_app_do_not_clash(tmp_path: Path) -> None:
    write(tmp_path / "user", "steam-2000", profile("Steam", "game.exe", STEAM))
    write(tmp_path / "user", "retail-2000", profile("Retail", "game.exe", RETAIL))

    assert {standing for standing, _ in standings(tmp_path).values()} == {Standing.USED}


def test_disabling_the_users_profile_brings_back_the_bundled_one(tmp_path: Path) -> None:
    write(tmp_path / "bundled", "game-2000", profile("Game", "game.exe"))
    write(tmp_path / "user", "my-game-2000", profile("My game", "game.exe"))

    assert standings(tmp_path, disabled=("my-game-2000",))["game-2000"] == (Standing.USED, None)


def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "user", tmp_path / "bundled", SCHEMAS)


def test_a_profile_is_added_once_checked_and_replaced_only_when_asked(tmp_path: Path) -> None:
    profiles = store(tmp_path)

    path = profiles.add("my-game-2000", profile("My game"), replace=False)

    assert path == tmp_path / "user" / "my-game-2000.json"
    assert json.loads(path.read_text("utf-8"))["app"]["title"] == "My game"
    with pytest.raises(ProfileExistsError, match="already have a profile named my-game-2000.json"):
        profiles.add("my-game-2000", profile("Again"), replace=False)
    profiles.add("my-game-2000", profile("Again"), replace=True)
    assert json.loads(path.read_text("utf-8"))["app"]["title"] == "Again"


def test_a_broken_profile_or_a_bad_name_is_refused_and_nothing_written(tmp_path: Path) -> None:
    profiles = store(tmp_path)

    with pytest.raises(ProfileError, match="mine-2000.json: must contain a JSON object"):
        profiles.add("mine-2000", [], replace=False)
    with pytest.raises(ProfileChangeError, match="cannot be the name of a profile"):
        profiles.add("My Game", profile("My game"), replace=False)
    assert not (tmp_path / "user").exists()


def test_a_bundled_profile_is_copied_to_replace_it_and_removing_the_copy_brings_it_back(tmp_path: Path) -> None:
    write(tmp_path / "bundled", "game-2000", profile("Game"))
    profiles = store(tmp_path)

    path = profiles.copy("game-2000")

    assert path.read_text("utf-8") == (tmp_path / "bundled" / "game-2000.json").read_text("utf-8")
    assert [entry.origin for entry in profiles.load()] == [Origin.OVERRIDE]
    with pytest.raises(ProfileExistsError, match="edit that one"):
        profiles.copy("game-2000")
    profiles.remove("game-2000")
    assert [entry.origin for entry in profiles.load()] == [Origin.BUNDLED]
    with pytest.raises(ProfileChangeError, match="cannot be removed: disable it instead"):
        profiles.remove("game-2000")
    with pytest.raises(ProfileChangeError, match="not a bundled profile"):
        profiles.copy("other-2000")
