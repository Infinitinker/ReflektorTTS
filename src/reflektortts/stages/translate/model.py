"""Translation models in the per-user data folder, downloaded on first use."""

import hashlib
import logging
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import platformdirs

logger = logging.getLogger(__name__)

# What the stage needs from an Argos Translate package; its sentence splitter (stanza) is left out.
_KEPT = ("model", "bpe.model", "README.md")


@dataclass(frozen=True)
class ModelPackage:
    """A translation model for one language pair, packaged by Argos Translate."""

    source: str
    target: str
    url: str
    sha256: str
    size_mb: int

    @property
    def name(self) -> str:
        return f"{self.source}-{self.target}"


PACKAGES = {
    ("en", "pl"): ModelPackage(
        source="en",
        target="pl",
        url="https://argos-net.com/v1/translate-en_pl-1_9.argosmodel",
        sha256="85d865369326b6d8220876fbd7bc552fa5ec8b99e81161fab4a26f78187cedbc",
        size_mb=64,
    ),
}


class ModelDownloadError(Exception):
    """A translation model could not be downloaded or unpacked."""


def models_dir() -> Path:
    return platformdirs.user_data_path("reflektortts", appauthor=False) / "translation"


def download_file(url: str, destination: Path) -> None:
    # argos-net.com refuses Python's default User-Agent.
    request = urllib.request.Request(url, headers={"User-Agent": "ReflektorTTS"})
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as file:
        shutil.copyfileobj(response, file)


def ensure_model(
    package: ModelPackage,
    directory: Path | None = None,
    download: Callable[[str, Path], None] = download_file,
) -> Path:
    """Returns the folder of a package's model, downloading it first if it is missing."""
    directory = directory or models_dir()
    model_dir = directory / package.name
    if (model_dir / "model" / "model.bin").is_file() and (model_dir / "bpe.model").is_file():
        return model_dir

    logger.info("Downloading the %s translation model (%d MB)", package.name, package.size_mb)
    directory.mkdir(parents=True, exist_ok=True)
    # Unpacking into a staging folder means an interrupted download never leaves a broken model behind.
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        archive = Path(staging) / "package.zip"
        try:
            download(package.url, archive)
        except OSError as error:
            raise ModelDownloadError(
                f"Could not download the {package.name} translation model: {error}. Check your internet connection."
            ) from error
        if _sha256(archive) != package.sha256:
            raise ModelDownloadError(f"The downloaded {package.name} translation model is damaged. Try again later.")
        unpacked = Path(staging) / "unpacked"
        _unpack(archive, unpacked)
        if model_dir.exists():
            shutil.rmtree(model_dir)
        unpacked.replace(model_dir)
    return model_dir


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _unpack(archive: Path, destination: Path) -> None:
    """Extracts the kept files, dropping the package's top-level folder."""
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            parts = PurePosixPath(member.filename).parts[1:]
            if member.is_dir() or not parts or parts[0] not in _KEPT or ".." in parts:
                continue
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("wb") as file:
                shutil.copyfileobj(source, file)
