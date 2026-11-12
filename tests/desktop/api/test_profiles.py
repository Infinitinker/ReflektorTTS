"""What the desktop app shows of the profiles: items, details, medals and profiles not set up."""

from typing import Any

from reflektortts.desktop.api.profiles import (
    STATES,
    ExecutableItem,
    ProfileItem,
    SourceItem,
    details_text,
    name_text,
    overlay_text,
    parse_profiles,
    rating_text,
    summary_text,
)

GTA2: dict[str, Any] = {
    "id": "grand-theft-auto-2-1999",
    "title": "Grand Theft Auto 2",
    "year": 1999,
    "origin": "bundled",
    "state": "reading",
    "reason": None,
    "file": r"C:\ReflektorTTS\profiles\bundled\grand-theft-auto-2-1999.json",
    "overlay": True,
    "rating": "gold",
    "executables": [{"name": "gta2.exe", "sha256": ["420a"]}],
    "sources": [{"name": "messages", "type": "memory", "stages": ["tracker", "replace"]}],
}
BROKEN: dict[str, Any] = GTA2 | {
    "id": "mine-2000",
    "title": None,
    "year": None,
    "origin": "custom",
    "state": "broken",
    "reason": "mine-2000.json: must contain a JSON object.",
    "file": r"C:\Users\me\profiles\mine-2000.json",
    "overlay": None,
    "rating": None,
    "executables": [],
    "sources": [],
}
GOLD = "Gold: The main texts are read, tested through most of the app."


def test_a_listing_from_the_api_becomes_items() -> None:
    [gta2, broken] = parse_profiles({"profiles": [GTA2, BROKEN]})

    assert gta2 == ProfileItem(
        id="grand-theft-auto-2-1999",
        title="Grand Theft Auto 2",
        year=1999,
        origin="bundled",
        state="reading",
        reason=None,
        file=r"C:\ReflektorTTS\profiles\bundled\grand-theft-auto-2-1999.json",
        overlay=True,
        rating="gold",
        executables=(ExecutableItem("gta2.exe", ("420a",)),),
        sources=(SourceItem("messages", "memory", ("tracker", "replace")),),
    )
    assert (name_text(gta2), overlay_text(gta2)) == ("Grand Theft Auto 2 (1999)", "Yes")
    assert (name_text(broken), overlay_text(broken)) == ("mine-2000.json", "")
    assert summary_text([gta2, broken]) == "2 profiles, 1 used"


def test_the_details_give_the_reason_and_the_medal_first_then_executables_and_sources() -> None:
    any_build = GTA2 | {"executables": [{"name": "gta2.exe", "sha256": []}]}
    [gta2, broken] = parse_profiles({"profiles": [any_build, BROKEN]})

    assert details_text(gta2) == f"{GOLD}\n\ngta2.exe: any version\nmessages (memory): tracker, replace"
    assert details_text(broken) == "mine-2000.json: must contain a JSON object."


def test_the_medal_is_named_with_what_it_means_and_a_profile_without_one_is_not_rated() -> None:
    [gta2, unrated, broken] = parse_profiles({"profiles": [GTA2, GTA2 | {"rating": None}, BROKEN]})

    assert rating_text(gta2) == ("Gold", "The main texts are read, tested through most of the app.")
    assert rating_text(unrated) == ("Not rated", "Its author did not say how far it is tested.")
    assert rating_text(broken) == ("", "")


def test_a_profile_not_set_up_is_named_so_and_not_counted_as_used() -> None:
    reason = "Not read until the VLC integration is enabled."
    [vlc] = parse_profiles({"profiles": [GTA2 | {"state": "not_set_up", "reason": reason}]})

    assert STATES[vlc.state] == "Not set up"
    assert summary_text([vlc]) == "1 profiles, 0 used"
    assert details_text(vlc).startswith(f"{reason}\n\n{GOLD}\n\n")
