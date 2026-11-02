import sys
from pathlib import Path

import pytest

from reflektortts.stages.translate.engine import (
    MosesBpeEngine,
    SentencePieceEngine,
    TranslationUnavailableError,
    join_name_endings,
    prepare,
    restore,
)


@pytest.mark.parametrize(
    ("detokenized", "joined"),
    [
        ("Zabij Frenzy 'ego!", "Zabij Frenzy'ego!"),
        ("Daj to Joe 'mu.", "Daj to Joe'mu."),
        ("Powiedział 'tak' i wyszedł.", "Powiedział 'tak' i wyszedł."),
        ("Misja zakończona!", "Misja zakończona!"),
    ],
)
def test_polish_name_endings_are_joined_to_the_name(detokenized: str, joined: str) -> None:
    assert join_name_endings(detokenized) == joined


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
    assert prepare(sentence) == prepared
    assert restore(sentence, translated) == restored


def test_missing_translation_packages_are_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ctranslate2", None)

    with pytest.raises(TranslationUnavailableError, match=r"pip install reflektortts\[translate\]"):
        MosesBpeEngine(tmp_path, "en", "pl")


def test_missing_sentencepiece_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentencepiece", None)

    with pytest.raises(TranslationUnavailableError, match=r"pip install reflektortts\[translate\]"):
        SentencePieceEngine(tmp_path)
