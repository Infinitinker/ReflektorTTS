"""Piper voices from their published list: listing, checking, installing and removing them, also offline."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reflektortts.downloads.http import PARALLEL_REQUESTS
from reflektortts.downloads.piper import FILE_URL, INDEX_URL, PAGE_URL, PiperVoices
from reflektortts.downloads.source import DownloadError, Entry, Kind
from tests.downloads.fake_web import FakeWeb

MODEL, CONFIG = b"model weights", b'{"audio": {}}'


def voice(family: str, code: str, name: str, model: bytes = MODEL) -> tuple[str, dict[str, Any]]:
    key = f"{code}-{name}-medium"
    folder = f"{family}/{code}/{name}/medium"
    files = {
        f"{folder}/{key}.onnx": {"size_bytes": len(MODEL), "md5_digest": hashlib.md5(model).hexdigest()},
        f"{folder}/{key}.onnx.json": {"size_bytes": len(CONFIG), "md5_digest": hashlib.md5(CONFIG).hexdigest()},
        f"{folder}/MODEL_CARD": {"size_bytes": 10, "md5_digest": "x"},
    }
    return key, {"key": key, "language": {"family": family, "code": code}, "quality": "medium", "files": files}


def web() -> FakeWeb:
    voices = dict([voice("pl", "pl_PL", "gosia"), voice("en", "en_US", "ljspeech"), voice("xx", "xx_XX", "unknown")])
    files = {INDEX_URL: json.dumps(voices).encode()}
    for key, info in voices.items():
        for path in info["files"]:
            if path.endswith("MODEL_CARD"):
                files[FILE_URL + path] = f"# Model card for {key}\n\nDataset: CC0".encode()
            elif path.endswith(".onnx"):
                files[FILE_URL + path] = MODEL
            else:
                files[FILE_URL + path] = CONFIG
    return FakeWeb(files)


def source(tmp_path: Path, fake: FakeWeb) -> PiperVoices:
    return PiperVoices(tmp_path / "cache", tmp_path / "voices", fake.fetch, fake.download)


def test_voices_in_known_languages_are_listed_with_their_model_card(tmp_path: Path) -> None:
    entries = source(tmp_path, web()).entries(refresh=True)

    assert [entry.id for entry in entries] == ["piper:en_US-ljspeech-medium", "piper:pl_PL-gosia-medium"]
    gosia = entries[1]
    assert gosia == Entry(
        id="piper:pl_PL-gosia-medium",
        kind=Kind.VOICE,
        name="pl_PL-gosia-medium",
        languages=("pl",),
        size=len(MODEL) + len(CONFIG),
        license="# Model card for pl_PL-gosia-medium\n\nDataset: CC0",
        page=PAGE_URL + "pl/pl_PL/gosia/medium",
        installed=False,
        source_title="Piper",
    )


def test_a_downloaded_voice_is_checked_installed_and_listed_as_installed(tmp_path: Path) -> None:
    fake = web()
    voices = source(tmp_path, fake)
    gosia = voices.entries(refresh=True)[1]
    reported: list[tuple[int, int | None]] = []

    voices.download(gosia, lambda done, total: reported.append((done, total)))

    assert sorted(path.name for path in (tmp_path / "voices").iterdir()) == [
        "pl_PL-gosia-medium.onnx",
        "pl_PL-gosia-medium.onnx.json",
    ]
    assert reported[-1] == (len(MODEL) + len(CONFIG), len(MODEL) + len(CONFIG))
    assert voices.entries(refresh=False)[1].installed


def test_a_damaged_voice_is_rejected_and_leaves_nothing(tmp_path: Path) -> None:
    fake = web()
    voices = source(tmp_path, fake)
    gosia = voices.entries(refresh=True)[1]
    fake.files[FILE_URL + "pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx"] = b"something else"

    with pytest.raises(DownloadError, match="damaged"):
        voices.download(gosia, lambda done, total: None)

    assert list((tmp_path / "voices").iterdir()) == []


def test_a_removed_voice_is_gone(tmp_path: Path) -> None:
    voices = source(tmp_path, web())
    gosia = voices.entries(refresh=True)[1]
    voices.download(gosia, lambda done, total: None)

    voices.remove(gosia)

    assert list((tmp_path / "voices").iterdir()) == []


def test_offline_the_saved_list_is_shown_with_the_cards_read_before(tmp_path: Path) -> None:
    fake = web()
    source(tmp_path, fake).entries(refresh=True)
    fake.offline = True

    entries = source(tmp_path, fake).entries(refresh=True)

    assert len(entries) == 2 and all(entry.license is not None for entry in entries)


def test_a_refresh_fetches_the_cards_that_changed(tmp_path: Path) -> None:
    fake = web()
    voices = source(tmp_path, fake)
    voices.entries(refresh=True)
    card = "pl/pl_PL/gosia/medium/MODEL_CARD"
    fake.files[FILE_URL + card] = b"# Retrained"
    index = json.loads(fake.files[INDEX_URL])
    index["pl_PL-gosia-medium"]["files"][card]["md5_digest"] = "y"
    fake.files[INDEX_URL] = json.dumps(index).encode()

    assert voices.entries(refresh=False)[1].license != "# Retrained"
    fake.fetched.clear()
    assert voices.entries(refresh=True)[1].license == "# Retrained"
    assert fake.fetched == [INDEX_URL, FILE_URL + card]


def test_a_voice_the_installed_piper_cannot_run_is_listed_only_once_installed(tmp_path: Path) -> None:
    fake = web()
    fake.files[FILE_URL + "pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx.json"] = b'{"phoneme_type": "japanese"}'
    voices = source(tmp_path, fake)

    assert [entry.name for entry in voices.entries(refresh=True)] == ["en_US-ljspeech-medium"]
    (tmp_path / "voices").mkdir()
    for name in ("pl_PL-gosia-medium.onnx", "pl_PL-gosia-medium.onnx.json"):
        (tmp_path / "voices" / name).write_bytes(MODEL)
    assert [entry.name for entry in voices.entries(refresh=False)] == ["en_US-ljspeech-medium", "pl_PL-gosia-medium"]


def test_norwegian_voices_are_listed_under_bokmal(tmp_path: Path) -> None:
    key, info = voice("no", "no_NO", "talesyntese")
    fake = FakeWeb({INDEX_URL: json.dumps({key: info}).encode()})

    entries = source(tmp_path, fake).entries(refresh=False)

    assert [entry.languages for entry in entries] == [("nb",)]


def test_without_a_connection_or_a_saved_list_the_list_cannot_be_shown(tmp_path: Path) -> None:
    fake = web()
    fake.offline = True

    with pytest.raises(DownloadError, match="internet connection"):
        source(tmp_path, fake).entries(refresh=True)


@pytest.mark.parametrize("name", [r"..\..\x", "../x", ".hidden", "C:x", "a b"])
def test_a_voice_whose_name_cannot_be_a_file_name_is_skipped(tmp_path: Path, name: str) -> None:
    fake = web()
    voices = json.loads(fake.files[INDEX_URL])
    _, info = voice("pl", "pl_PL", "gosia")
    voices[name] = info
    fake.files[INDEX_URL] = json.dumps(voices).encode()

    entries = source(tmp_path, fake).entries(refresh=True)

    assert [entry.name for entry in entries] == ["en_US-ljspeech-medium", "pl_PL-gosia-medium"]


def test_listing_again_without_a_refresh_never_fetches_missing_cards(tmp_path: Path) -> None:
    fake = web()
    voices = source(tmp_path, fake)
    fake.files = {url: data for url, data in fake.files.items() if not url.endswith("MODEL_CARD")}
    voices.entries(refresh=True)
    fake.files = web().files
    fake.fetched.clear()

    entries = voices.entries(refresh=False)

    assert fake.fetched == []
    assert all(entry.license is None for entry in entries)


def test_the_first_listing_reads_which_voices_piper_can_run_without_a_refresh(tmp_path: Path) -> None:
    fake = web()
    fake.files[FILE_URL + "pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx.json"] = b'{"phoneme_type": "pinyin"}'

    entries = source(tmp_path, fake).entries(refresh=False)

    assert [entry.name for entry in entries] == ["en_US-ljspeech-medium"]


def test_once_a_file_cannot_be_fetched_the_rest_are_not_tried(tmp_path: Path) -> None:
    fake = web()
    voices = source(tmp_path, fake)
    voices.entries(refresh=False)
    fake.offline = True
    index = json.loads(fake.files[INDEX_URL])
    for info in index.values():
        for file in info["files"].values():
            file["md5_digest"] = "changed"
    (tmp_path / "cache" / "voices.json").write_text(json.dumps(index))
    fake.fetched.clear()

    entries = voices.entries(refresh=True)

    assert len(fake.fetched) <= 1 + 2 * PARALLEL_REQUESTS
    assert all(entry.license is not None for entry in entries)


def test_folders_left_by_an_unfinished_download_are_removed_at_start(tmp_path: Path) -> None:
    left = tmp_path / "voices" / ".staging-abc"
    left.mkdir(parents=True)
    (left / "pl_PL-gosia-medium.onnx").write_bytes(b"part")

    source(tmp_path, web())

    assert not left.exists()


def test_a_missing_card_does_not_stop_the_others_being_read(tmp_path: Path) -> None:
    fake = web()
    del fake.files[FILE_URL + "en/en_US/ljspeech/medium/MODEL_CARD"]

    entries = source(tmp_path, fake).entries(refresh=True)

    assert [entry.license is not None for entry in entries] == [False, True]
