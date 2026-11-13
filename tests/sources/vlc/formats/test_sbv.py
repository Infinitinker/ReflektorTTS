"""YouTube SubViewer (.sbv) subtitles: cues that end at a blank line or at the next timing line."""

from reflektortts.sources.vlc.formats.sbv import parse_sbv


def texts(text: str) -> list[tuple[float, float, str]]:
    return [(cue.start, cue.end, cue.text) for cue in parse_sbv(text)]


def test_cues_are_read_until_a_blank_line() -> None:
    text = "0:00:01.000,0:00:04.000\nWelcome\nto the show.\n\n1:00:05.500,1:00:09.000\nLast line"

    assert texts(text) == [(1.0, 4.0, "Welcome to the show."), (3605.5, 3609.0, "Last line")]


def test_crlf_and_extra_blank_lines_are_handled() -> None:
    text = "\r\n0:00:01.000,0:00:02.000\r\nOne\r\n\r\n\r\n0:00:03.000,0:00:04.000\r\nTwo\r\n"

    assert texts(text) == [(1.0, 2.0, "One"), (3.0, 4.0, "Two")]


def test_a_timing_line_ends_the_cue_before_it_when_the_blank_line_is_missing() -> None:
    text = "0:00:01.000,0:00:02.000\nOne\n0:00:03.000,0:00:04.000\nTwo"

    assert texts(text) == [(1.0, 2.0, "One"), (3.0, 4.0, "Two")]


def test_lines_outside_a_cue_are_skipped() -> None:
    text = "stray\n0:00:01.000 0:00:02.000\nnot a cue\n\n0:00:03.000,0:00:04.000\nKept\n\nafter it\n"

    assert texts(text) == [(3.0, 4.0, "Kept")]
