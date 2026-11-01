import io
import sys
import zipfile
from pathlib import Path

import pytest

from reflektortts.stages.translate import model
from reflektortts.stages.translate.model import ModelInstallError, install_archive, installed_model, remove_model
from tests.stages.translate.fake_package import PACKAGE_BYTES, package_bytes

PAIR = ("en", "pl")


def archive(tmp_path: Path, data: bytes = PACKAGE_BYTES) -> Path:
    path = tmp_path / "package.argosmodel"
    path.write_bytes(data)
    return path


def test_a_package_is_installed_without_its_sentence_splitter(tmp_path: Path) -> None:
    models = tmp_path / "models"

    model_dir = install_archive(archive(tmp_path), PAIR, models)

    assert model_dir == models / "en-pl" == installed_model(PAIR, models)
    files = sorted(path.relative_to(model_dir).as_posix() for path in model_dir.rglob("*") if path.is_file())
    assert files == ["README.md", "bpe.model", "model/config.json", "model/model.bin"]
    assert list(models.iterdir()) == [model_dir]


def test_a_package_with_a_sentencepiece_tokenizer_is_installed(tmp_path: Path) -> None:
    models = tmp_path / "models"

    model_dir = install_archive(archive(tmp_path, package_bytes("sentencepiece.model")), PAIR, models)

    assert installed_model(PAIR, models) == model_dir
    assert (model_dir / "sentencepiece.model").is_file()


def test_a_package_without_a_tokenizer_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ModelInstallError, match="not a translation model"):
        install_archive(archive(tmp_path, package_bytes("other.model")), PAIR, tmp_path / "models")


def test_a_damaged_package_is_rejected_and_leaves_nothing(tmp_path: Path) -> None:
    models = tmp_path / "models"

    with pytest.raises(ModelInstallError, match="damaged"):
        install_archive(archive(tmp_path, PACKAGE_BYTES[:-10]), PAIR, models)

    assert installed_model(PAIR, models) is None
    assert list(models.iterdir()) == []


def test_a_removed_model_is_no_longer_installed(tmp_path: Path) -> None:
    models = tmp_path / "models"
    install_archive(archive(tmp_path), PAIR, models)

    remove_model(PAIR, models)

    assert installed_model(PAIR, models) is None


def with_member(name: str) -> bytes:
    """The test package with one more file, named as given."""
    archive = io.BytesIO(PACKAGE_BYTES)
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr(name, "planted")
    return archive.getvalue()


def assert_refused(tmp_path: Path, name: str) -> None:
    models = tmp_path / "models"

    with pytest.raises(ModelInstallError, match="safely"):
        install_archive(archive(tmp_path, with_member(name)), PAIR, models)

    assert installed_model(PAIR, models) is None
    assert list(models.iterdir()) == []
    assert not any(path.name == "planted.py" for path in tmp_path.rglob("*"))


def test_a_package_with_a_file_leading_out_of_its_folder_is_refused(tmp_path: Path) -> None:
    assert_refused(tmp_path, "translate-en_pl-1_9/model/../../planted.py")


@pytest.mark.skipif(sys.platform != "win32", reason="Drive letters and backslashes are path syntax only on Windows")
def test_a_package_with_a_windows_path_leading_out_of_its_folder_is_refused(tmp_path: Path) -> None:
    # "X:name" is relative to the current folder of drive X, so it escapes only from another drive.
    other_drive = "C" if tmp_path.drive.upper() != "C:" else "D"
    assert_refused(tmp_path, f"translate-en_pl-1_9/model/{other_drive}:planted.py")
    assert_refused(tmp_path, r"translate-en_pl-1_9/model\..\..\planted.py")


def test_a_package_too_big_to_be_a_model_is_refused_before_unpacking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model, "MAX_UNPACKED_BYTES", 10)
    models = tmp_path / "models"

    with pytest.raises(ModelInstallError, match="safely"):
        install_archive(archive(tmp_path), PAIR, models)

    assert list(models.iterdir()) == []
