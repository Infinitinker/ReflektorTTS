from pathlib import Path

import pytest

from reflektortts.settings import Settings, load_settings, save_settings
from reflektortts.tts.engine import DEFAULT_VOICE


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "settings.json") == Settings(voice=DEFAULT_VOICE)


def test_saved_settings_load_back(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"

    save_settings(Settings(voice="windows:Microsoft Adam"), path)

    assert load_settings(path) == Settings(voice="windows:Microsoft Adam")
    assert not path.with_suffix(".tmp").exists()


def test_broken_file_is_reported_and_defaults_are_used(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{oops", "utf-8")

    assert load_settings(path) == Settings()
    assert "Cannot read settings" in caplog.text


def test_unknown_or_wrongly_typed_fields_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"voice": 5, "future_option": true}', "utf-8")

    assert load_settings(path) == Settings()
