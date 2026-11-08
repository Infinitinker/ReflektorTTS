"""The bundled VLC profile: subtitles' marks for the hard of hearing and for music are not read."""

import pytest

from reflektortts.events import TextEvent
from reflektortts.profiles.catalog import BUNDLED_DIR
from reflektortts.profiles.loader import load_profile
from reflektortts.stages.replace import create

PROFILE = load_profile(BUNDLED_DIR / "vlc-media-player-2001.json")


def cleaned(text: str) -> str:
    (source,) = PROFILE.sources
    (rules,) = [stage.settings for stage in source.stages if stage.type == "replace"]
    event = create(rules, {}).process(TextEvent(source="subtitles", text=text, time=0.0))
    assert event is not None
    return event.text


def test_the_profile_reads_any_vlc_build_without_the_overlay() -> None:
    assert not PROFILE.overlay
    assert [(executable.name, executable.sha256) for executable in PROFILE.match.executables] == [
        ("vlc.exe", ()),
        ("vlc", ()),
    ]
    assert [source.type for source in PROFILE.sources] == ["vlc"]


@pytest.mark.parametrize(
    ("text", "result"),
    [
        ("[door slams] Who's there?", "Who's there?"),
        ("(SIGHS) Fine.", "Fine."),
        ("♪ Humming along ♪ Hey.", "Hey."),
        ("♪ la la la", ""),
        ("- Are you coming? - In a minute.", "Are you coming? In a minute."),
        ("-[gasps] - No!", "No!"),
        ("Well - maybe.", "Well maybe."),
        ("Twenty-five years.", "Twenty-five years."),
    ],
)
def test_marks_for_sounds_music_and_dialogue_dashes_are_removed(text: str, result: str) -> None:
    assert cleaned(text) == result
