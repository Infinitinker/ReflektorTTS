"""How the desktop app names languages: a language by both its names, a translation by an arrow."""

from reflektortts.desktop.api.languages import LanguageItem, languages_text, parse_languages, speech_rules_text

LANGUAGES = parse_languages(
    {
        "languages": [
            {"code": "en", "name": "English", "english_name": "English", "speech_rules": ["Numbers"]},
            {"code": "pl", "name": "Polski", "english_name": "Polish", "speech_rules": ["Grammar", "Numbers, dates"]},
            {"code": "de", "name": "Deutsch", "english_name": "German", "speech_rules": []},
        ]
    }
)


def test_the_languages_are_read_by_code() -> None:
    assert LANGUAGES["pl"] == LanguageItem("pl", "Polski", "Polish", ("Grammar", "Numbers, dates"))


def test_a_language_is_named_in_english_then_in_itself() -> None:
    assert languages_text(("pl",), LANGUAGES) == "Polish (Polski)"


def test_a_language_whose_names_are_the_same_is_named_once() -> None:
    assert languages_text(("en",), LANGUAGES) == "English"


def test_a_translation_is_named_by_its_languages_english_names() -> None:
    assert languages_text(("en", "pl"), LANGUAGES) == "English → Polish"


def test_a_language_s_speech_rules_are_set_apart_by_dots_since_they_may_hold_commas() -> None:
    assert speech_rules_text("pl", LANGUAGES) == "Grammar · Numbers, dates"
    assert speech_rules_text("en", LANGUAGES) == "Numbers"
    assert speech_rules_text("de", LANGUAGES) == ""
    assert speech_rules_text("xx", LANGUAGES) == ""


def test_a_language_the_core_does_not_list_is_named_by_its_code() -> None:
    assert languages_text(("xx",), LANGUAGES) == "xx"
    assert languages_text(("en", "xx"), LANGUAGES) == "English → xx"
