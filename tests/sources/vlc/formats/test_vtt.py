"""WebVTT (.vtt, .webvtt) subtitles: cues, the blocks skipped, and the tags, timestamps and entities in their text."""

from reflektortts.sources.vlc.formats.vtt import parse_vtt


def texts(text: str) -> list[tuple[float, float, str]]:
    return [(cue.start, cue.end, cue.text) for cue in parse_vtt(text)]


def test_cues_are_read_with_or_without_identifiers_and_hours() -> None:
    text = (
        "WEBVTT - Example captions\n"
        "Kind: captions\n"
        "\n"
        "intro\n"
        "00:00:01.000 --> 00:00:02.500\n"
        "Hello there.\n"
        "\n"
        "00:03.000 --> 00:04.000 align:start line:0 position:10%\n"
        "Two\n"
        "lines.\n"
    )

    assert texts(text) == [(1.0, 2.5, "Hello there."), (3.0, 4.0, "Two lines.")]


def test_note_style_and_region_blocks_are_skipped() -> None:
    text = (
        "WEBVTT\n\n"
        "NOTE This file was made by hand.\n00:00:00.500 --> 00:00:00.900\n\n"
        "STYLE\n::cue { color: yellow }\n\n"
        "REGION\nid:speaker width:40%\n\n"
        "NOTE\nmore notes\n\n"
        "00:00:01.000 --> 00:00:02.000\nKept\n"
    )

    assert texts(text) == [(1.0, 2.0, "Kept")]


def test_tags_and_inline_timestamps_are_removed_and_ruby_readings_dropped() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:05.000\n"
        "<v.loud Anna>Run,</v> <c.yellow.bg_blue>now</c> <i>and</i> <b>fast</b> <u>here</u>\n"
        "<lang pl>Dzień</lang> <00:00:02.000>dobry <ruby>漢<rt>kan</rt></ruby>字 <ruby>a<rt>b</ruby>\n"
    )

    assert texts(text) == [(1.0, 5.0, "Run, now and fast here Dzień dobry 漢字 a")]


def test_every_tag_is_removed_but_escaped_angle_brackets_are_kept() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\n"
        '<font color="red">A</font> <span class=x>B</span> &lt;b&gt;literal&lt;/b&gt;\n'
    )

    assert texts(text) == [(1.0, 2.0, "A B <b>literal</b>")]


def test_a_cue_right_after_the_header_line_is_read() -> None:
    assert texts("WEBVTT\n00:00:01.000 --> 00:00:02.000\nHello\n\n00:00:03.000 --> 00:00:04.000\nAgain\n") == [
        (1.0, 2.0, "Hello"),
        (3.0, 4.0, "Again"),
    ]
    assert texts("WEBVTT\nKind: captions\n00:00:01.000 --> 00:00:02.000\nHello\n") == [(1.0, 2.0, "Hello")]


def test_entities_are_decoded_and_direction_marks_dropped() -> None:
    text = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nTom &amp; Jerry &lt;3 &gt;&nbsp;x&lrm;y&rlm;\n"

    assert texts(text) == [(1.0, 2.0, "Tom & Jerry <3 > xy")]


def test_crlf_is_handled() -> None:
    text = (
        "WEBVTT\r\n\r\n1\r\n00:00:01.000 --> 00:00:02.000\r\nOne\r\n\r\n2\r\n00:00:03.000 --> 00:00:04.000\r\nTwo\r\n"
    )

    assert texts(text) == [(1.0, 2.0, "One"), (3.0, 4.0, "Two")]


def test_blocks_without_a_timing_line_are_skipped() -> None:
    text = "WEBVTT\n\nstray text\n\nid\nnot a timing\nText\n\n00:00:01.000 --> 00:00:02.000\nOne\n"

    assert texts(text) == [(1.0, 2.0, "One")]


def test_a_file_without_the_webvtt_header_has_no_cues() -> None:
    assert texts("00:00:01.000 --> 00:00:02.000\nOne\n") == []
    assert texts("WEBVTTX\n\n00:00:01.000 --> 00:00:02.000\nOne\n") == []
    assert texts("") == []
