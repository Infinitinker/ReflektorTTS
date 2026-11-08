import pytest

from reflektortts.desktop.api.status import (
    CoreStatus,
    describe,
    hint,
    languages_text,
    parse_status,
    settings_caption,
    sound_text,
)


def test_a_status_event_gives_the_game_and_whether_reading_is_paused() -> None:
    event = {"type": "status", "app": {"title": "Mad Max", "pid": 42}, "paused": True, "voice": "piper:a"}

    assert parse_status(event) == CoreStatus(app="Mad Max", paused=True, voice="piper:a")
    assert parse_status({"type": "status", "app": None, "paused": False}) == CoreStatus(app=None, paused=False)


def test_a_status_event_gives_the_profile_the_app_is_read_with() -> None:
    event = {"type": "status", "app": {"title": "GTA2", "pid": 7, "profile": "gta2"}, "paused": False}

    assert parse_status(event) == CoreStatus(app="GTA2", paused=False, profile="gta2")


def test_other_events_are_not_a_status() -> None:
    assert parse_status({"type": "line", "source": "subtitles", "text": "Hi"}) is None


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (None, "Starting…"),
        (CoreStatus(app=None, paused=False), "Waiting for an app"),
        (CoreStatus(app="Mad Max", paused=False), "Reading Mad Max"),
        (CoreStatus(app="Mad Max", paused=True), "Reading Mad Max (paused)"),
    ],
)
def test_the_status_in_a_few_words(status: CoreStatus | None, text: str) -> None:
    assert describe(status) == text


def test_an_unsupported_version_is_described_with_its_hash() -> None:
    event = {"type": "status", "app": None, "paused": False, "unsupported": {"title": "Mad Max", "sha256": "abc"}}

    status = parse_status(event)

    assert status == CoreStatus(app=None, paused=False, unsupported="Mad Max", unsupported_sha256="abc")
    assert describe(status) == "This version of Mad Max is not supported yet"
    assert hint(status) == "To support it, its profile needs this version's SHA-256: abc"
    assert hint(CoreStatus(app=None, paused=False)) == "In an app with the overlay, open the panel with Ctrl+Shift+R."


def test_a_status_event_gives_the_voice_languages_and_app_sound() -> None:
    event = {
        "type": "status",
        "app": None,
        "paused": False,
        "voice": "windows:Microsoft Adam",
        "input_language": "en",
        "output_language": "pl",
        "ducking": True,
        "duck_volume": 0.3,
    }

    status = parse_status(event)

    assert status is not None
    assert status.voice == "windows:Microsoft Adam"
    assert languages_text(status, {"en": "English", "pl": "Polski"}.__getitem__) == "English → Polski"
    assert sound_text(status) == "Lowered to 30% while a line is spoken"


def test_one_language_is_named_once_and_unlowered_sound_is_said() -> None:
    status = CoreStatus(app=None, paused=False, input_language="pl", output_language="pl", ducking=False)

    assert languages_text(status, {"pl": "Polski"}.__getitem__) == "Polski"
    assert sound_text(status) == "Not lowered while a line is spoken"


def test_the_details_say_whose_settings_they_are() -> None:
    assert settings_caption(None) == ""
    assert settings_caption(CoreStatus(app=None, paused=False)) == "Settings a new app starts with:"
    assert settings_caption(CoreStatus(app="Mad Max", paused=False)) == "Settings for Mad Max:"


def test_the_source_error_of_the_app_being_read_is_what_to_do_now() -> None:
    event = {
        "type": "status",
        "app": {"title": "VLC media player", "pid": 42},
        "paused": False,
        "source_error": {"source": "subtitles", "message": "VLC's web interface is off."},
    }

    status = parse_status(event)

    assert status == CoreStatus(app="VLC media player", paused=False, source_error="VLC's web interface is off.")
    assert hint(status) == "VLC's web interface is off."
    assert parse_status(event | {"source_error": None}) == CoreStatus(app="VLC media player", paused=False)
