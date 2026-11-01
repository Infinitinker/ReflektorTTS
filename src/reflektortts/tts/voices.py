"""Piper voices in the per-user data folder. The Piper download source (downloads/piper.py)
installs them; nothing here downloads."""

from pathlib import Path

from reflektortts.user_dirs import data_dir


def voices_dir() -> Path:
    return data_dir() / "voices"


def voice_files(name: str) -> tuple[str, str]:
    """A voice's model and its config, e.g. "en_US-ljspeech-medium.onnx" and ".onnx.json"."""
    return f"{name}.onnx", f"{name}.onnx.json"


def downloaded_voices(directory: Path | None = None) -> list[str]:
    """Names of voices whose model and config are both in the folder."""
    directory = directory or voices_dir()
    return sorted(
        model.name.removesuffix(".onnx")
        for model in directory.glob("*.onnx")
        if model.with_name(f"{model.name}.json").is_file()
    )
