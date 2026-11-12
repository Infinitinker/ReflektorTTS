"""The subtitle formats read: each by its extension and in any encoding, and other formats not read."""

from pathlib import Path

import pytest

from reflektortts.sources.vlc.formats import decode, format_of, read_cues

SAMPLES = {
    ".srt": "1\n00:00:01,000 --> 00:00:02,000\nZażółć\n",
    ".vtt": "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nZażółć\n",
    ".webvtt": "WEBVTT\n\n00:01.000 --> 00:02.000\nZażółć\n",
    ".ass": "[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Zażółć\n",
    ".ssa": "[Events]\nDialogue: Marked=0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Zażółć\n",
    ".sbv": "0:00:01.000,0:00:02.000\nZażółć\n",
}


@pytest.mark.parametrize("suffix", list(SAMPLES))
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1250"])
def test_each_format_is_read_by_its_extension_in_any_encoding(suffix: str, encoding: str) -> None:
    file_format = format_of(Path(f"Movie.EN{suffix.upper()}"))
    assert file_format is not None

    cues = read_cues(file_format, SAMPLES[suffix].replace("\n", "\r\n").encode(encoding), "cp1250")

    assert [(cue.start, cue.end, cue.text) for cue in cues.cues] == [(1.0, 2.0, "Zażółć")]


@pytest.mark.parametrize("name", ["movie.sub", "movie.stl", "movie.idx", "movie.ttml", "movie"])
def test_other_formats_are_not_read(name: str) -> None:
    assert format_of(Path(name)) is None


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ("Zażółć".encode("utf-8-sig"), "Zażółć"),
        ("Zażółć".encode("utf-16"), "Zażółć"),
        (b"\xfe\xff" + "Zażółć".encode("utf-16-be"), "Zażółć"),
        ("Zażółć".encode(), "Zażółć"),
        ("Zażółć".encode("cp1250"), "Zażółć"),
    ],
)
def test_text_is_decoded_as_utf_8_or_utf_16_or_else_the_fallback(data: bytes, text: str) -> None:
    assert decode(data, "cp1250") == text
