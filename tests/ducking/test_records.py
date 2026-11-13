"""The record of apps' original volumes while they are lowered: kept by process name, a broken file read as none."""

from pathlib import Path

from reflektortts.ducking.records import DuckRecords


def test_records_are_kept_by_process_name_and_the_file_goes_when_empty(tmp_path: Path) -> None:
    path = tmp_path / "lowered-apps.json"
    records = DuckRecords(path)

    records.put("GTA2.exe", 0.8)

    assert DuckRecords(path).get("gta2.exe") == 0.8
    records.remove("gta2.exe")
    assert records.get("gta2.exe") is None
    assert not path.exists()


def test_a_broken_file_reads_as_no_records(tmp_path: Path) -> None:
    path = tmp_path / "lowered-apps.json"
    path.write_text("{not json", "utf-8")

    assert DuckRecords(path).get("gta2.exe") is None
