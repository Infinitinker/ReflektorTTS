"""Piper voices in the per-user data folder, downloaded on first use."""

import tempfile
from collections.abc import Callable
from pathlib import Path

import platformdirs

# Trained on the public-domain LJ Speech dataset, so it can be bundled and used by default.
DEFAULT_VOICE = "en_US-ljspeech-medium"


class VoiceDownloadError(Exception):
    """A voice could not be downloaded."""


def voices_dir() -> Path:
    return platformdirs.user_data_path("reflektortts", appauthor=False) / "voices"


def ensure_voice(
    name: str,
    directory: Path | None = None,
    download: Callable[[str, Path], None] | None = None,
) -> Path:
    """Returns the path of a voice's model, downloading the voice first if it is missing."""
    if download is None:
        # Piper pulls in onnxruntime; importing it only when needed keeps it out of the core process.
        from piper.download_voices import download_voice

        download = download_voice
    directory = directory or voices_dir()
    files = [f"{name}.onnx", f"{name}.onnx.json"]
    model = directory / files[0]
    if all((directory / file).is_file() for file in files):
        return model

    directory.mkdir(parents=True, exist_ok=True)
    # Downloading into a staging folder means an interrupted download never leaves a
    # broken voice behind.
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        try:
            download(name, Path(staging))
        except (OSError, ValueError) as error:
            raise VoiceDownloadError(
                f"Could not download the voice {name}: {error}. Check your internet connection."
            ) from error
        for file in files:
            (Path(staging) / file).replace(directory / file)
    return model
