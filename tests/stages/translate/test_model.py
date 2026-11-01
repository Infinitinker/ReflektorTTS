from pathlib import Path

import pytest

from reflektortts.stages.translate.model import ModelInstallError, install_archive, installed_model, remove_model
from tests.stages.translate.fake_package import PACKAGE_BYTES

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
