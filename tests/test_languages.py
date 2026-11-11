import pytest

from reflektortts.languages import (
    LANGUAGES,
    SAMPLES,
    Language,
    LanguageError,
    check_language,
    language_name,
    language_tag,
    other_codes,
    primary_language,
    sample,
)


def test_every_iso_639_1_language_is_known_with_its_names_and_codes() -> None:
    assert len(LANGUAGES) == 182
    assert LANGUAGES["de"] == Language("de", "Deutsch", "German", "ger", "deu", "cp1252", True)
    assert LANGUAGES["pl"].name == "Polski"
    assert LANGUAGES["sr"].code_page == "cp1251"
    assert not LANGUAGES["ja"].separates_words and LANGUAGES["ja"].code_page == "cp932"


@pytest.mark.parametrize(("tag", "code"), [("pl-PL", "pl"), ("en_US", "en"), ("no_NO", "nb"), ("fil-PH", "tl")])
def test_a_tag_s_language_is_a_code_here(tag: str, code: str) -> None:
    assert primary_language(tag) == code


@pytest.mark.parametrize(
    ("tag", "normalized"), [("no_NO", "nb-NO"), ("fil-PH", "tl-PH"), ("pl-PL", "pl-PL"), ("en", "en")]
)
def test_a_voice_s_tag_names_its_language_by_the_code_here(tag: str, normalized: str) -> None:
    assert language_tag(tag) == normalized


def test_an_unknown_language_is_an_error_that_says_what_a_code_looks_like() -> None:
    with pytest.raises(LanguageError, match='There is no language "auto": use its two-letter ISO 639-1 code'):
        check_language("auto")


def test_a_voice_preview_speaks_a_sample_or_the_language_s_own_name() -> None:
    assert sample("en") == "This is how this voice reads your apps."
    assert sample("ru") == "Русский"
    with pytest.raises(LanguageError):
        sample("xx")


def test_samples_are_for_known_languages() -> None:
    assert set(SAMPLES) <= set(LANGUAGES)


def test_messages_name_languages_in_english() -> None:
    assert language_name("de") == "German"
    assert language_name("xx") == '"xx"'


def test_norwegian_is_one_language_known_by_bokmal_s_code() -> None:
    assert "no" not in LANGUAGES
    assert other_codes("nb") == {"no", "nor"}
    assert other_codes("de") == set()


def test_a_code_known_here_by_another_is_refused_with_the_code_to_use() -> None:
    with pytest.raises(LanguageError, match=r'Use "nb" \(Norwegian Bokmål\) instead of "no"'):
        check_language("no")
