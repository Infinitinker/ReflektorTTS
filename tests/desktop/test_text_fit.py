from reflektortts.desktop.text_fit import ELLIPSIS, FittedText, fit_lines


def measure(text: str) -> int:
    """Every character is 10 pixels wide."""
    return 10 * len(text)


def test_short_text_stays_on_one_line() -> None:
    assert fit_lines("Waiting for an app", 300, measure, 2) == FittedText(["Waiting for an app"], cut=False)


def test_text_wraps_at_spaces() -> None:
    assert fit_lines("one two three four", 100, measure, 2) == FittedText(["one two", "three four"], cut=False)


def test_text_longer_than_the_lines_is_cut_with_an_ellipsis() -> None:
    fitted = fit_lines("one two three four five six", 100, measure, 2)

    assert fitted == FittedText(["one two", f"three fou{ELLIPSIS}"], cut=True)
    assert all(measure(line) <= 100 for line in fitted.lines)


def test_a_word_longer_than_a_line_is_broken() -> None:
    assert fit_lines("SHA-256: 0123456789abcdef", 100, measure, 3) == FittedText(
        ["SHA-256: 0", "123456789a", "bcdef"], cut=False
    )


def test_a_word_too_long_for_any_line_starts_after_the_words_before_it() -> None:
    assert fit_lines("put abcdefghijkl", 100, measure, 2) == FittedText(["put abcdef", "ghijkl"], cut=False)


def test_a_word_that_fits_a_line_of_its_own_goes_to_the_next_line() -> None:
    assert fit_lines("put abcdefgh", 100, measure, 2) == FittedText(["put", "abcdefgh"], cut=False)


def test_line_breaks_in_the_text_are_kept() -> None:
    assert fit_lines("one\ntwo", 300, measure, 2) == FittedText(["one", "two"], cut=False)


def test_empty_text_is_one_empty_line() -> None:
    assert fit_lines("", 300, measure, 2) == FittedText([""], cut=False)


def test_whitespace_around_the_text_is_dropped() -> None:
    assert fit_lines("  one\ntwo\n", 300, measure, 2) == FittedText(["one", "two"], cut=False)
    assert fit_lines(" \n ", 300, measure, 2) == FittedText([""], cut=False)


def test_a_cut_at_a_line_break_ends_the_last_line_kept_with_an_ellipsis() -> None:
    assert fit_lines("one\ntwo\nthree", 300, measure, 2) == FittedText(["one", f"two{ELLIPSIS}"], cut=True)


def test_a_width_narrower_than_the_ellipsis_still_ends() -> None:
    fitted = fit_lines("one two three", 5, measure, 2)

    assert fitted.cut
    assert fitted.lines[-1] == ELLIPSIS


def test_only_the_lines_kept_are_measured() -> None:
    calls = 0

    def counting(text: str) -> int:
        nonlocal calls
        calls += 1
        return measure(text)

    fit_lines("word " * 2000, 300, counting, 2)

    assert calls < 100
