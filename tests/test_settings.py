from pathlib import Path

import pytest

from reflektortts.settings import Settings, load_settings, save_settings
from reflektortts.tts.engine import DEFAULT_VOICE


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "settings.json") == Settings(voice=DEFAULT_VOICE)


def test_saved_settings_load_back(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    settings = Settings(
        voice="windows:Microsoft Adam",
        game_language="en",
        speech_language="pl",
        voices_by_language={"pl": "windows:Microsoft Adam"},
        disabled_stages={"grand-theft-auto-2-1999": ["messages/2:normalize"]},
    )

    save_settings(settings, path)

    assert load_settings(path) == settings
    assert not path.with_suffix(".tmp").exists()


def test_the_old_language_setting_becomes_the_speech_language(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"voice": "piper:a", "language": "pl"}', "utf-8")

    assert load_settings(path) == Settings(voice="piper:a", speech_language="pl")


def test_broken_file_is_reported_and_defaults_are_used(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{oops", "utf-8")

    assert load_settings(path) == Settings()
    assert "Cannot read settings" in caplog.text


def test_unknown_or_wrongly_typed_fields_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"voice": 5, "future_option": true, "voices_by_language": {"pl": 1}, "disabled_stages": []}', "utf-8"
    )

    assert load_settings(path) == Settings()
