from pathlib import Path

from reflektortts.tts.voices import downloaded_voices, voice_files


def test_a_voice_is_installed_with_both_its_files(tmp_path: Path) -> None:
    for file in voice_files("pl_PL-whole-medium"):
        (tmp_path / file).write_bytes(b"")
    (tmp_path / "en_US-half-medium.onnx").write_bytes(b"")

    assert downloaded_voices(tmp_path) == ["pl_PL-whole-medium"]
