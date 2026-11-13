"""Translation models from Argos Translate's package index: listing, installing and removing them."""

import json
from pathlib import Path

import pytest

from reflektortts.downloads.argos import INDEX_URL, PAGE_URL, TITLE, ArgosModels
from reflektortts.downloads.source import DownloadError, Entry, Kind
from reflektortts.stages.translate.model import installed_model
from tests.downloads.fake_web import FakeWeb
from tests.stages.translate.fake_package import PACKAGE_BYTES

EN_PL = "https://example.invalid/translate-en_pl.argosmodel"


def package(source: str, target: str, link: str) -> dict[str, object]:
    return {
        "from_code": source,
        "to_code": target,
        "from_name": source,
        "to_name": target,
        "links": [link],
    }


def web() -> FakeWeb:
    index = [
        package("en", "pl", EN_PL),
        package("pl", "en", "https://example.invalid/translate-pl_en.argosmodel"),
        package("en", "xx", "https://example.invalid/translate-en_xx.argosmodel"),
    ]
    return FakeWeb({INDEX_URL: json.dumps(index).encode(), EN_PL: PACKAGE_BYTES})


def source(tmp_path: Path, fake: FakeWeb) -> ArgosModels:
    return ArgosModels(tmp_path / "cache", tmp_path / "models", fake.fetch, fake.download, fake.size)


def test_models_between_known_languages_are_listed_with_an_unknown_license(tmp_path: Path) -> None:
    entries = source(tmp_path, web()).entries(refresh=True)

    assert entries == [
        Entry(
            "argos:en-pl",
            Kind.TRANSLATION,
            "English → Polish",
            ("en", "pl"),
            len(PACKAGE_BYTES),
            None,
            PAGE_URL,
            False,
            TITLE,
        ),
        Entry("argos:pl-en", Kind.TRANSLATION, "Polish → English", ("pl", "en"), None, None, PAGE_URL, False, TITLE),
    ]


def test_a_downloaded_model_is_installed_for_its_pair(tmp_path: Path) -> None:
    models = source(tmp_path, web())
    en_pl = models.entries(refresh=True)[0]

    models.download(en_pl, lambda done, total: None)

    assert installed_model(("en", "pl"), tmp_path / "models") is not None
    assert models.entries(refresh=False)[0].installed


def test_a_download_that_is_not_a_model_is_rejected(tmp_path: Path) -> None:
    fake = web()
    models = source(tmp_path, fake)
    en_pl = models.entries(refresh=True)[0]
    fake.files[EN_PL] = b"<html>not found</html>"

    with pytest.raises(DownloadError, match="damaged"):
        models.download(en_pl, lambda done, total: None)

    assert installed_model(("en", "pl"), tmp_path / "models") is None


def test_a_removed_model_is_no_longer_installed(tmp_path: Path) -> None:
    models = source(tmp_path, web())
    en_pl = models.entries(refresh=True)[0]
    models.download(en_pl, lambda done, total: None)

    models.remove(en_pl)

    assert not models.entries(refresh=False)[0].installed


def test_a_model_under_an_alias_is_listed_under_the_language_code_unless_one_is_there(tmp_path: Path) -> None:
    index = [
        package("en", "zt", "https://example.invalid/translate-en_zt.argosmodel"),
        package("en", "zh", "https://example.invalid/translate-en_zh.argosmodel"),
        package("pb", "en", "https://example.invalid/translate-pb_en.argosmodel"),
    ]
    fake = FakeWeb({INDEX_URL: json.dumps(index).encode()})

    entries = source(tmp_path, fake).entries(refresh=False)

    assert [(entry.id, entry.name) for entry in entries] == [
        ("argos:en-zh", "English → Chinese"),
        ("argos:pt-en", "Portuguese → English"),
    ]
