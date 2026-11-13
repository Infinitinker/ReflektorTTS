"""Preparing sentences for the translation model and putting its translation back: capitals, full stops and spaces."""

import pytest

from reflektortts.stages.translate.engine import join_pieces, join_sentences, prepare, restore


@pytest.mark.parametrize(
    ("sentence", "prepared", "translated", "restored"),
    [
        (
            "But we gotta keep it tight",
            "But we gotta keep it tight.",
            "Ale musimy trzymać się kupy.",
            "Ale musimy trzymać się kupy",
        ),
        ("Ryder, you fool!", "Ryder, you fool!", "Ryder, ty głupcze!", "Ryder, ty głupcze!"),
        ("a bank in Palomino Creek,", "a bank in Palomino Creek,", "bank w Palomino Creek,", "bank w Palomino Creek,"),
        ("Wait for it", "Wait for it.", "Czekaj...", "Czekaj..."),
        ("GOODBYE!", "Goodbye!", "Do widzenia!", "DO WIDZENIA!"),
        ("BERKLEY YOU BASTARD", "Berkley you bastard.", "Berkley, ty draniu.", "BERKLEY, TY DRANIU"),
        ("I DID IT, I SAID!", "I did it, I said!", "Zrobiłem to, powiedziałem!", "ZROBIŁEM TO, POWIEDZIAŁEM!"),
        ("Hey, MADD DOGG!", "Hey, MADD DOGG!", "Hej, MADD DOGG!", "Hej, MADD DOGG!"),
    ],
)
def test_a_sentence_is_translated_the_way_the_model_does_best_then_put_back(
    sentence: str, prepared: str, translated: str, restored: str
) -> None:
    assert prepare(sentence, "en") == prepared
    assert restore(sentence, translated) == restored


def test_a_shouted_sentence_keeps_the_capital_i_only_in_english() -> None:
    assert prepare("TY I JA!", "pl") == "Ty i ja!"
    assert prepare("YOU AND I!", "en") == "You and I!"


@pytest.mark.parametrize(
    ("decoded", "joined"),
    [
        ("Kevin,▁give me the▁keys.", "Kevin, give me the keys."),
        ("▁Où est l'argent ?", "Où est l'argent ?"),
        ("la▁voiture,  on▁doit▁partir.", "la voiture, on doit partir."),
        ("snake_case stays", "snake_case stays"),
    ],
)
def test_word_marks_the_tokenizer_leaves_become_spaces(decoded: str, joined: str) -> None:
    assert join_pieces(decoded) == joined


def test_a_japanese_sentence_without_an_ending_gets_its_full_stop_and_loses_it_again() -> None:
    assert prepare("元気です", "ja") == "元気です。"
    assert restore("元気です", "I'm fine.") == "I'm fine"
    assert restore("I'm fine", "元気です。") == "元気です"


def test_sentences_are_joined_without_spaces_in_languages_written_without_them() -> None:
    assert join_sentences(["Wait.", "What?"], "en") == "Wait. What?"
    assert join_sentences(["待って。", "何？"], "ja") == "待って。何？"
    assert join_sentences(["รอก่อน", "อะไร"], "th") == "รอก่อน อะไร"


def test_a_hindi_sentence_ending_in_a_vowel_sign_gets_a_full_stop_that_its_translation_loses() -> None:
    assert prepare("ठीक है", "hi") == "ठीक है."
    assert restore("Wait", "रुको।") == "रुको"
    assert restore("Wait", "رکو۔") == "رکو"
