"""Translation models in the per-user data folder, one folder per language pair (e.g. "en-pl").

Models are Argos Translate packages; the Argos download source (downloads/argos.py) installs them
with install_archive. Nothing here downloads.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from reflektortts.user_dirs import data_dir

type Pair = tuple[str, str]
"""(game language, output language)"""

# What the stage needs from an Argos Translate package; its sentence splitter (stanza) is left out.
_KEPT = ("model", "bpe.model", "README.md")


class ModelInstallError(Exception):
    """A downloaded translation model cannot be installed."""


class ModelNotInstalledError(Exception):
    """No translation model is installed for a pair of languages."""


def models_dir() -> Path:
    return data_dir() / "translation"


def model_dir(pair: Pair, directory: Path | None = None) -> Path:
    return (directory or models_dir()) / f"{pair[0]}-{pair[1]}"


def installed_model(pair: Pair, directory: Path | None = None) -> Path | None:
    """The folder of the pair's model if it is installed, else None."""
    folder = model_dir(pair, directory)
    return folder if _is_model(folder) else None


def _is_model(folder: Path) -> bool:
    return (folder / "model" / "model.bin").is_file() and (folder / "bpe.model").is_file()


def install_archive(archive: Path, pair: Pair, directory: Path | None = None) -> Path:
    """Installs a downloaded Argos package as the pair's model, replacing an older one."""
    target = model_dir(pair, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Unpacking into a staging folder means a broken archive never leaves a broken model behind.
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        unpacked = Path(staging) / "unpacked"
        try:
            _unpack(archive, unpacked)
        except (zipfile.BadZipFile, OSError) as error:
            raise ModelInstallError(f"The downloaded translation model is damaged: {error}. Try again.") from error
        if not _is_model(unpacked):
            raise ModelInstallError("The downloaded file is not a translation model ReflektorTTS can use.")
        if target.exists():
            shutil.rmtree(target)
        unpacked.replace(target)
    return target


def remove_model(pair: Pair, directory: Path | None = None) -> None:
    shutil.rmtree(model_dir(pair, directory), ignore_errors=True)


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
