import os
from pathlib import Path

import pytest

from reflektortts.downloads.cache import save


def test_a_list_is_saved_whole(tmp_path: Path) -> None:
    save(tmp_path / "cache" / "voices.json", b"{}")

    assert [path.name for path in (tmp_path / "cache").iterdir()] == ["voices.json"]
    assert (tmp_path / "cache" / "voices.json").read_bytes() == b"{}"


def test_a_save_that_fails_leaves_the_old_list_and_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save(tmp_path / "voices.json", b"old")

    def fail(_source: str, _target: Path) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        save(tmp_path / "voices.json", b"new")

    assert [path.name for path in tmp_path.iterdir()] == ["voices.json"]
    assert (tmp_path / "voices.json").read_bytes() == b"old"
