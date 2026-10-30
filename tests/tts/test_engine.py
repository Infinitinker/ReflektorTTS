import sys

import pytest

from reflektortts.tts.engine import EnginePlugin, Voice, VoiceError, load_engine_plugin, parse_voice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("windows:Microsoft Adam", Voice("windows", "Microsoft Adam")),
        ("Piper: en_US-ljspeech-medium", Voice("piper", "en_US-ljspeech-medium")),
        ("en_US-ljspeech-medium", Voice("piper", "en_US-ljspeech-medium")),
    ],
)
def test_parse_voice(text: str, expected: Voice) -> None:
    assert parse_voice(text) == expected


def test_unknown_engine_lists_the_installed_ones() -> None:
    with pytest.raises(VoiceError, match=r'no speech engine called "espeak" \(installed: .*piper'):
        load_engine_plugin("espeak")


def test_piper_engine_is_registered() -> None:
    plugin = load_engine_plugin("piper")

    assert isinstance(plugin, EnginePlugin)
    assert plugin.name == "piper"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows voices exist only on Windows")
def test_windows_engine_is_registered() -> None:
    assert load_engine_plugin("windows").name == "windows"
