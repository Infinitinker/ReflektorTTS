import pytest

from reflektortts.sources.vlc.formats.cues import Cue, Cues, collect, seconds


def test_the_cue_shown_is_the_one_that_started_last_and_has_not_ended() -> None:
    cues = Cues([Cue(1.0, 5.0, "Long"), Cue(2.0, 3.0, "Short"), Cue(6.0, 7.0, "Later")])

    assert cues.at(0.5) is None
    assert cues.at(1.0) == "Long"
    assert cues.at(2.5) == "Short"
    assert cues.at(3.5) is None
    assert cues.at(5.5) is None
    assert cues.at(6.9) == "Later"
    assert cues.at(7.0) is None


@pytest.mark.parametrize(
    ("parts", "value"),
    [(("1", "02", "03", "5"), 3723.5), (("0", "00", "01", "25"), 1.25), ((None, "01", "02", "003"), 62.003)],
)
def test_a_fraction_s_digits_are_its_first_decimals(parts: tuple[str | None, str, str, str], value: float) -> None:
    assert seconds(*parts) == pytest.approx(value)


def test_cues_that_start_together_become_one_in_file_order() -> None:
    cues = collect([Cue(1.0, 3.0, "Anna: Hi."), Cue(5.0, 6.0, "Later"), Cue(1.0, 5.0, "Ben: Hello.")])

    assert cues.cues == (Cue(1.0, 5.0, "Anna: Hi. Ben: Hello."), Cue(5.0, 6.0, "Later"))
    assert cues.at(4.0) == "Anna: Hi. Ben: Hello."


def test_a_text_repeated_among_cues_that_start_together_is_read_once() -> None:
    cues = collect([Cue(1.0, 3.0, "Same"), Cue(1.0, 4.0, "Other"), Cue(1.0, 5.0, "Same"), Cue(6.0, 7.0, "Same")])

    assert cues.cues == (Cue(1.0, 5.0, "Same Other"), Cue(6.0, 7.0, "Same"))


def test_cues_that_end_before_they_start_or_have_no_text_are_dropped() -> None:
    assert len(collect([Cue(5.0, 4.0, "Backwards"), Cue(6.0, 6.0, "Instant"), Cue(7.0, 8.0, "")])) == 0
