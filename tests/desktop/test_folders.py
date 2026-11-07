from pathlib import Path

import pytest

from reflektortts.desktop import folders


def test_explorer_is_started_by_its_full_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started: list[list[str]] = []
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("SystemRoot", r"D:\Windows")
    monkeypatch.setattr("subprocess.Popen", started.append)

    folders.open_folder(tmp_path / "logs")
    folders.show_file(tmp_path / "a.json")

    explorer = str(Path(r"D:\Windows") / "explorer.exe")
    assert started == [[explorer, str(tmp_path / "logs")], [explorer, f"/select,{tmp_path / 'a.json'}"]]
    assert (tmp_path / "logs").is_dir()
