import sys
from pathlib import Path

import pytest

from reflektortts.stages.translate.engine import MosesBpeEngine, TranslationUnavailableError


def test_missing_translation_packages_are_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ctranslate2", None)

    with pytest.raises(TranslationUnavailableError, match=r"pip install reflektortts\[translate\]"):
        MosesBpeEngine(tmp_path, "en", "pl")
