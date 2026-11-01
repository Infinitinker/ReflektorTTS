from pathlib import Path

from reflektortts.staging import remove_leftovers, staging_folder


def test_a_staging_folder_is_removed_when_done(tmp_path: Path) -> None:
    with staging_folder(tmp_path / "voices") as staging:
        assert Path(staging).parent == tmp_path / "voices"
        (Path(staging) / "voice.onnx").write_bytes(b"part")

    assert list((tmp_path / "voices").iterdir()) == []


def test_folders_left_by_a_cut_off_download_are_removed_and_nothing_else(tmp_path: Path) -> None:
    left = tmp_path / ".staging-abc"
    left.mkdir()
    (left / "voice.onnx").write_bytes(b"part")
    installed = tmp_path / "en-pl"
    installed.mkdir()

    remove_leftovers(tmp_path)

    assert not left.exists()
    assert installed.is_dir()
