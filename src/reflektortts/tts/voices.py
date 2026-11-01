"""Piper voices in the per-user data folder. ensure_voice downloads one, when the player asks for it;
nothing downloads a voice by itself."""

import tempfile
from collections.abc import Callable
from pathlib import Path

from reflektortts.user_dirs import data_dir


class VoiceDownloadError(Exception):
    """A voice could not be downloaded."""


def voices_dir() -> Path:
    return data_dir() / "voices"


def downloaded_voices(directory: Path | None = None) -> list[str]:
    """Names of voices whose model and config are both in the folder."""
    directory = directory or voices_dir()
    return sorted(
        model.name.removesuffix(".onnx")
        for model in directory.glob("*.onnx")
        if model.with_name(f"{model.name}.json").is_file()
    )


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
