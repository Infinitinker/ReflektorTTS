import sys
from pathlib import Path

import pytest

from reflektortts.stages.translate.engine import (
    MosesBpeEngine,
    SentencePieceEngine,
    TranslationUnavailableError,
    join_name_endings,
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


def test_missing_translation_packages_are_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ctranslate2", None)

    with pytest.raises(TranslationUnavailableError, match=r"pip install reflektortts\[translate\]"):
        MosesBpeEngine(tmp_path, "en", "pl")


def test_missing_sentencepiece_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentencepiece", None)

    with pytest.raises(TranslationUnavailableError, match=r"pip install reflektortts\[translate\]"):
        SentencePieceEngine(tmp_path)
