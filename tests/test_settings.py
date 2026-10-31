import json
from pathlib import Path

import pytest

from reflektortts.settings import GameSettings, SharedSettings, load_game, load_shared, save_game, save_shared

GTA2 = "grand-theft-auto-2-1999"


def test_on_the_first_run_there_are_no_files_and_everything_has_defaults(tmp_path: Path) -> None:
    config = tmp_path / "ReflektorTTS"

    assert load_shared(config) == SharedSettings()
    assert load_game(config, GTA2) == GameSettings()
    assert not config.exists()


def test_a_games_settings_load_back_from_its_own_file(tmp_path: Path) -> None:
    settings = GameSettings(
        voice="windows:Microsoft Adam",
        game_language="pl",
        output_language="pl",
        disabled_stages=("messages/2:normalize",),
    )

    save_game(settings, tmp_path / "config", GTA2)

    assert load_game(tmp_path / "config", GTA2) == settings
    assert (tmp_path / "config" / "games" / f"{GTA2}.json").is_file()
    assert not (tmp_path / "config" / "games" / f"{GTA2}.tmp").exists()


def test_shared_settings_load_back(tmp_path: Path) -> None:
    settings = SharedSettings(voices_by_language={"pl": "windows:Microsoft Adam"})

    save_shared(settings, tmp_path)

    assert load_shared(tmp_path) == settings


@pytest.mark.parametrize("language", ["auto", "xx", 5])
def test_an_unsupported_game_language_becomes_english(tmp_path: Path, language: object) -> None:
    (tmp_path / "games").mkdir()
    (tmp_path / "games" / f"{GTA2}.json").write_text(json.dumps({"game_language": language}), "utf-8")

    assert load_game(tmp_path, GTA2).game_language == "en"


def test_a_broken_file_is_reported_and_defaults_are_used(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "settings.json").write_text("{oops", "utf-8")

    assert load_shared(tmp_path) == SharedSettings()
    assert "Cannot read settings" in caplog.text


def test_unknown_or_wrongly_typed_fields_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "games").mkdir()
    (tmp_path / "games" / f"{GTA2}.json").write_text(
        '{"voice": 5, "future_option": true, "disabled_stages": {"a": 1}, "disabled_sources": ["ok", 2]}', "utf-8"
    )

    assert load_game(tmp_path, GTA2) == GameSettings(disabled_sources=("ok",))
