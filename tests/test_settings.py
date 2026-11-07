import json
from pathlib import Path

import pytest

from reflektortts.events import Output
from reflektortts.settings import (
    ProfileSettings,
    SharedSettings,
    load_profile_settings,
    load_shared,
    save_profile_settings,
    save_shared,
)

GTA2 = "grand-theft-auto-2-1999"


def test_on_the_first_run_there_are_no_files_and_everything_has_defaults(tmp_path: Path) -> None:
    config = tmp_path / "ReflektorTTS"

    assert load_shared(config) == SharedSettings()
    assert load_profile_settings(config, GTA2) == ProfileSettings()
    assert not config.exists()


def test_a_games_settings_load_back_from_its_own_file(tmp_path: Path) -> None:
    settings = ProfileSettings(
        voice="windows:Microsoft Adam",
        input_language="pl",
        output_language="pl",
        stage_switches={"messages/2:normalize": {Output.TEXT: True, Output.SPEECH: False}},
    )

    save_profile_settings(settings, tmp_path / "config", GTA2)

    assert load_profile_settings(tmp_path / "config", GTA2) == settings
    assert (tmp_path / "config" / "settings" / "profiles" / f"{GTA2}.json").is_file()
    assert not (tmp_path / "config" / "settings" / "profiles" / f"{GTA2}.tmp").exists()


def test_shared_settings_load_back(tmp_path: Path) -> None:
    settings = SharedSettings(voices_by_language={"pl": "windows:Microsoft Adam"})

    save_shared(settings, tmp_path)

    assert load_shared(tmp_path) == settings


@pytest.mark.parametrize("language", ["auto", "xx", 5])
def test_an_unsupported_input_language_becomes_english(tmp_path: Path, language: object) -> None:
    (tmp_path / "settings" / "profiles").mkdir(parents=True)
    (tmp_path / "settings" / "profiles" / f"{GTA2}.json").write_text(json.dumps({"input_language": language}), "utf-8")

    assert load_profile_settings(tmp_path, GTA2).input_language == "en"


def test_a_broken_file_is_reported_and_defaults_are_used(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "shared.json").write_text("{oops", "utf-8")

    assert load_shared(tmp_path) == SharedSettings()
    assert "Cannot read settings" in caplog.text


def test_unknown_or_wrongly_typed_fields_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "settings" / "profiles").mkdir(parents=True)
    data = {
        "voice": 5,
        "future_option": True,
        "stage_switches": {"a": {"text": 1, "sound": True, "speech": False}, "b": []},
        "disabled_sources": ["ok", 2],
    }
    (tmp_path / "settings" / "profiles" / f"{GTA2}.json").write_text(json.dumps(data), "utf-8")

    assert load_profile_settings(tmp_path, GTA2) == ProfileSettings(
        disabled_sources=("ok",), stage_switches={"a": {Output.SPEECH: False}}
    )


def test_a_file_not_saved_as_utf8_is_reported_and_defaults_are_used(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "shared.json").write_text('{"voices_by_language": {"pl": "Paweł"}}', "cp1250")

    assert load_shared(tmp_path) == SharedSettings()
    assert "Cannot read settings" in caplog.text


def test_a_file_saved_with_a_byte_order_mark_loads(tmp_path: Path) -> None:
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "shared.json").write_text('{"voices_by_language": {"pl": "windows:Paweł"}}', "utf-8-sig")

    assert load_shared(tmp_path).voices_by_language == {"pl": "windows:Paweł"}
