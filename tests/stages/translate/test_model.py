import hashlib
import io
import zipfile
from pathlib import Path
from urllib.error import URLError

import pytest

from reflektortts.stages.translate.model import ModelDownloadError, ModelPackage, ensure_model


def package_bytes() -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("translate-en_pl-1_9/model/model.bin", b"weights")
        package.writestr("translate-en_pl-1_9/model/config.json", "{}")
        package.writestr("translate-en_pl-1_9/bpe.model", "#version: 0.2\n")
        package.writestr("translate-en_pl-1_9/README.md", "CC-BY 4.0")
        package.writestr("translate-en_pl-1_9/metadata.json", "{}")
        package.writestr("translate-en_pl-1_9/stanza/en/tokenize/default.pt", b"sentences")
    return archive.getvalue()


PACKAGE_BYTES = package_bytes()
PACKAGE = ModelPackage(
    "en", "pl", "https://example.invalid/en_pl.argosmodel", hashlib.sha256(PACKAGE_BYTES).hexdigest(), 1
)


def fake_download(url: str, destination: Path) -> None:
    destination.write_bytes(PACKAGE_BYTES)


def test_missing_model_is_downloaded_without_the_sentence_splitter(tmp_path: Path) -> None:
    model_dir = ensure_model(PACKAGE, tmp_path, download=fake_download)

    assert model_dir == tmp_path / "en-pl"
    files = sorted(path.relative_to(model_dir).as_posix() for path in model_dir.rglob("*") if path.is_file())
    assert files == ["README.md", "bpe.model", "model/config.json", "model/model.bin"]
    assert list(tmp_path.iterdir()) == [model_dir]


def test_present_model_is_not_downloaded_again(tmp_path: Path) -> None:
    ensure_model(PACKAGE, tmp_path, download=fake_download)

    def must_not_download(url: str, destination: Path) -> None:
        raise AssertionError("downloaded again")

    assert ensure_model(PACKAGE, tmp_path, download=must_not_download) == tmp_path / "en-pl"


def test_failed_download_raises_and_leaves_no_files(tmp_path: Path) -> None:
    def failing_download(url: str, destination: Path) -> None:
        destination.write_bytes(b"partial")
        raise URLError("no network")

    with pytest.raises(ModelDownloadError, match="internet connection"):
        ensure_model(PACKAGE, tmp_path, download=failing_download)

    assert list(tmp_path.iterdir()) == []


def test_damaged_download_is_rejected(tmp_path: Path) -> None:
    def damaged_download(url: str, destination: Path) -> None:
        destination.write_bytes(PACKAGE_BYTES[:-10])

    with pytest.raises(ModelDownloadError, match="damaged"):
        ensure_model(PACKAGE, tmp_path, download=damaged_download)

    assert list(tmp_path.iterdir()) == []
