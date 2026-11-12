"""SubStation Alpha (.ass, .ssa) subtitles: dialogue lines, the order of their fields, and override blocks removed."""

from reflektortts.sources.vlc.formats.ass import parse_ass
from reflektortts.sources.vlc.formats.cues import Cue, collect

HEADER = (
    "[Script Info]\n"
    "ScriptType: v4.00+\n"
    "\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize\n"
    "Style: Default,Arial,20\n"
    "\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def texts(text: str) -> list[tuple[float, float, str]]:
    return [(cue.start, cue.end, cue.text) for cue in parse_ass(text)]


def test_dialogue_lines_are_read_with_commas_in_their_text_and_line_breaks_as_spaces() -> None:
    text = HEADER + (
        "Dialogue: 0,0:00:01.00,0:00:04.50,Default,,0,0,0,,Well, hello,\\Nthere.\n"
        "Comment: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,A note for translators\n"
        "Dialogue: 0,1:02:03.25,1:02:04.00,Default,Anna,0,0,0,,Soft\\nbreak\\hand\\h\\hspace\n"
    )

    assert texts(text) == [(1.0, 4.5, "Well, hello, there."), (3723.25, 3724.0, "Soft break and space")]


def test_the_format_line_decides_the_field_order() -> None:
    text = (
        "[Events]\n"
        "Format: Start, End, Text\n"
        "Dialogue: 0:00:01.00,0:00:02.00,First, of all\n"
        "Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: Marked=0,0:00:03.00,0:00:04.00,Default,,0000,0000,0000,,SSA line\n"
    )

    assert texts(text) == [(1.0, 2.0, "First, of all"), (3.0, 4.0, "SSA line")]


def test_without_a_format_line_the_standard_fields_are_assumed() -> None:
    text = "[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Text\n"

    assert texts(text) == [(1.0, 2.0, "Text")]


def test_override_blocks_and_drawings_are_removed() -> None:
    text = HEADER + (
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an8\\pos(10,20)}{\\i1}Top{\\i0} {a comment}line\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,Sign {\\p1}m 0 0 l 100 0 100 100{\\p0}text\n"
        "Dialogue: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,{\\p2}m 0 0 l 10 10\n"
    )

    assert texts(text) == [(1.0, 2.0, "Top line"), (3.0, 4.0, "Sign text"), (5.0, 6.0, "")]


def test_other_sections_and_malformed_lines_are_skipped() -> None:
    text = (
        "[Script Info]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Not an event\n"
        "[Events]\r\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default\r\n"
        "Dialogue: 0,soon,0:00:02.00,Default,,0,0,0,,Bad time\r\n"
        "garbage\r\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,Kept\r\n"
        "[Fonts]\r\n"
        "Dialogue: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,Not an event either\r\n"
    )

    assert texts(text) == [(3.0, 4.0, "Kept")]


def test_simultaneous_events_become_one_cue_and_overlaps_show_the_latest() -> None:
    text = HEADER + (
        "Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,Anna: Hi.\n"
        "Dialogue: 1,0:00:01.00,0:00:03.00,Default,,0,0,0,,Ben: Hello.\n"
        "Dialogue: 0,0:00:02.00,0:00:04.00,Sign,,0,0,0,,EXIT\n"
    )

    cues = collect(parse_ass(text))

    assert cues.at(1.5) == "Anna: Hi. Ben: Hello."
    assert cues.at(3.0) == "EXIT"
    assert cues.at(4.5) is None


def test_a_line_drawn_again_on_another_layer_is_read_once() -> None:
    text = HEADER + (
        "Dialogue: 0,0:00:11.00,0:00:13.00,Default,,0,0,0,,{\\blur3\\3c&H000000&}Same text\n"
        "Dialogue: 1,0:00:11.00,0:00:13.00,Default,,0,0,0,,Same text\n"
    )

    assert collect(parse_ass(text)).cues == (Cue(11.0, 13.0, "Same text"),)
