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

# What the stage needs from an Argos Translate package (the model, and its BPE or SentencePiece
# tokenizer); its sentence splitter (stanza) is left out.
_KEPT = ("model", "bpe.model", "sentencepiece.model", "README.md")
_TOKENIZERS = ("bpe.model", "sentencepiece.model")
MAX_UNPACKED_BYTES = 1024**3
"""Real models unpack to a few hundred MB; a bigger package is refused before anything is unpacked."""
UNSAFE = "The downloaded file is not a translation model ReflektorTTS can use safely."


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
    return (folder / "model" / "model.bin").is_file() and any((folder / name).is_file() for name in _TOKENIZERS)


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
    """Extracts the kept files, dropping the package's top-level folder.

    Raises ModelInstallError, before writing anything, for a file that would land outside
    destination (e.g. "../x" or the drive-relative "D:x" on Windows) or a package that would unpack
    to more than MAX_UNPACKED_BYTES. Reading a file never yields more than its declared size, so
    the declared sizes can be trusted.
    """
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        kept = []
        for member in package.infolist():
            parts = PurePosixPath(member.filename).parts[1:]
            if member.is_dir() or not parts or parts[0] not in _KEPT:
                continue
            target = destination.joinpath(*parts)
            if not target.resolve().is_relative_to(root):
                raise ModelInstallError(UNSAFE)
            kept.append((member, target))
        if sum(member.file_size for member, _ in kept) > MAX_UNPACKED_BYTES:
            raise ModelInstallError(UNSAFE)
        for member, target in kept:
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("wb") as file:
                shutil.copyfileobj(source, file)
