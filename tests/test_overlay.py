import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from reflektortts.overlay import INJECTOR, WRONG_BITNESS, inject_overlay


def build(directory: Path) -> Path:
    directory.mkdir()
    (directory / INJECTOR).write_bytes(b"")
    return directory


def fake_run(exit_codes: dict[str, int], calls: list[list[str]]) -> Any:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, exit_codes[Path(command[0]).parent.name], "", "bad things")

    return run


def test_builds_are_tried_until_one_matches_the_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run({"x86": WRONG_BITNESS, "x64": 0}, calls))

    assert inject_overlay(42, [build(tmp_path / "x86"), build(tmp_path / "x64")]) is True
    assert [Path(call[0]).parent.name for call in calls] == ["x86", "x64"]
    assert calls[0][1:] == ["--pid", "42"]


def test_a_real_failure_stops_and_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run({"x86": 1, "x64": 0}, calls))

    assert inject_overlay(42, [build(tmp_path / "x86"), build(tmp_path / "x64")]) is False
    assert len(calls) == 1
    assert "bad things" in caplog.text


def test_injector_messages_are_read_as_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    message = "Overlay DLL not found: C:\\Users\\Łukasz\\reflektortts-overlay.dll"
    real_run = subprocess.run

    def injector(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        script = f"import sys; sys.stderr.buffer.write({message.encode('utf-8')!r}); sys.exit(1)"
        return real_run([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(subprocess, "run", injector)

    assert inject_overlay(42, [build(tmp_path / "x86")]) is False
    assert message in caplog.text


def test_an_injector_blocked_by_antivirus_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class BlockedByAntivirus(OSError):
        winerror = 225  # Only Windows' OSError has it, so it is set here, on every system.

    def blocked(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise BlockedByAntivirus("The file contains a virus")

    monkeypatch.setattr(subprocess, "run", blocked)

    assert inject_overlay(42, [build(tmp_path / "x86")]) is False
    assert "antivirus" in caplog.text


def test_an_injector_that_hangs_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def hangs(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", hangs)

    assert inject_overlay(42, [build(tmp_path / "x86")]) is False
    assert "did not finish" in caplog.text


def test_missing_injector_is_reported(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert inject_overlay(42, [tmp_path]) is False
    assert "No overlay in" in caplog.text
    assert "No overlay found; the app runs without the overlay." in caplog.text
    assert "32-bit vs 64-bit" not in caplog.text
