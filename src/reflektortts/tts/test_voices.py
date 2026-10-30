from pathlib import Path
from urllib.error import URLError

import pytest

from reflektortts.tts.voices import VoiceDownloadError, ensure_voice


def fake_download(name: str, directory: Path) -> None:
    (directory / f"{name}.onnx").write_bytes(b"model")
    (directory / f"{name}.onnx.json").write_text("{}")


def failing_download(name: str, directory: Path) -> None:
    (directory / f"{name}.onnx").write_bytes(b"partial")
    raise URLError("no network")


def test_missing_voice_is_downloaded(tmp_path: Path) -> None:
    model = ensure_voice("en_US-test-medium", tmp_path, download=fake_download)

    assert model == tmp_path / "en_US-test-medium.onnx"
    assert model.read_bytes() == b"model"
    assert (tmp_path / "en_US-test-medium.onnx.json").is_file()


def test_present_voice_is_not_downloaded_again(tmp_path: Path) -> None:
    ensure_voice("en_US-test-medium", tmp_path, download=fake_download)

    def must_not_download(name: str, directory: Path) -> None:
        raise AssertionError("downloaded again")

    assert ensure_voice("en_US-test-medium", tmp_path, download=must_not_download).is_file()


def test_failed_download_raises_and_leaves_no_files(tmp_path: Path) -> None:
    with pytest.raises(VoiceDownloadError, match="internet connection"):
        ensure_voice("en_US-test-medium", tmp_path, download=failing_download)

    assert list(tmp_path.iterdir()) == []
