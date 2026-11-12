"""SubRip (.srt) subtitles: cues found by their timing lines, with their lines joined and tags removed."""

from reflektortts.sources.vlc.formats.srt import parse_srt

BASIC = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "Hello there.\n"
    "\n"
    "2\n"
    "00:00:03,000 --> 00:00:04,000\n"
    "<i>Two</i> lines\n"
    'of <font color="#ff0000">text</font>.\n'
)


def texts(text: str) -> list[tuple[float, float, str]]:
    return [(cue.start, cue.end, cue.text) for cue in parse_srt(text)]


def test_cues_are_read_with_their_lines_joined_and_tags_removed() -> None:
    assert texts(BASIC) == [(1.0, 2.5, "Hello there."), (3.0, 4.0, "Two lines of text.")]


def test_crlf_and_a_missing_blank_line_and_a_blank_line_inside_a_cue_are_handled() -> None:
    text = "1\r\n00:00:01,000 --> 00:00:02,000\r\nOne\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nTwo\r\n\r\nstill two\r\n"

    assert texts(text) == [(1.0, 2.0, "One"), (3.0, 4.0, "Two still two")]


def test_short_hours_and_milliseconds_dots_and_coordinates_are_accepted() -> None:
    text = "0:01:02.5 --> 0:01:03.25  X1:100 X2:200 Y1:10 Y2:20\nShort\n"

    assert texts(text) == [(62.5, 63.25, "Short")]


def test_only_override_codes_in_braces_and_known_tags_are_removed() -> None:
    text = "00:00:01,000 --> 00:00:02,000\n{\\an8}Top {and braces} <3\n"

    assert texts(text) == [(1.0, 2.0, "Top {and braces} <3")]


def test_text_before_the_first_timing_line_is_skipped() -> None:
    text = "garbage\n\n1\n00:00:01,000 --> 00:00:02,000\nOne\n"

    assert texts(text) == [(1.0, 2.0, "One")]
