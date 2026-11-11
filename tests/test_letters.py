import re

from reflektortts.letters import WORD, WORD_CHARACTER, ends_in_letter, letter_count


def test_letters_are_counted_in_any_script_with_their_marks() -> None:
    assert letter_count("Okay!") == 4
    assert letter_count("हूँ") == 3
    assert letter_count("ไม่รู้") == 6
    assert letter_count("$100") == 0


def test_words_keep_their_marks() -> None:
    assert WORD.findall("movie.नेपाली.2019_cut") == ["movie", "नेपाली", "2019", "cut"]
    assert re.findall(rf"(?<!{WORD_CHARACTER})राम(?!{WORD_CHARACTER})", "रामू यहाँ है। राम आया।") == ["राम"]


def test_a_text_ending_in_a_vowel_sign_ends_in_a_letter() -> None:
    assert ends_in_letter("ठीक है")
    assert ends_in_letter("Wait")
    assert not ends_in_letter("Wait.")
    assert not ends_in_letter("")
