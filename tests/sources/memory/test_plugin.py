import pytest

from reflektortts.apps.detector import ProcessInfo, RunningApp
from reflektortts.pipeline.plugins import source_plugins
from reflektortts.process_memory.pointer import Address, PointerChain, UnsupportedAppVersion
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings
from reflektortts.sources.memory import plugin
from reflektortts.sources.memory.plugin import PLUGIN, parse_settings
from reflektortts.sources.memory.source import MemorySettings


def test_memory_plugin_is_registered_through_entry_points() -> None:
    assert source_plugins()["memory"] is PLUGIN


def test_parse_settings_turns_profile_fields_into_typed_settings() -> None:
    settings = parse_settings(
        {
            "encoding": "utf-16le",
            "pointers": [{"exe_sha256": "a" * 64, "address": "gta2.exe+272F40", "offsets": ["E4", "10"]}],
        }
    )

    assert settings == MemorySettings(
        encoding="utf-16le",
        pointers=(PointerChain(exe_sha256="a" * 64, base=Address("gta2.exe", 0x272F40), offsets=(0xE4, 0x10)),),
    )


SETTINGS = {
    "encoding": "utf-16le",
    "pointers": [
        {"exe_sha256": "a" * 64, "address": "gta2.exe+272F40", "offsets": []},
        {"exe_sha256": "b" * 64, "address": "gta2.exe+1000", "offsets": []},
    ],
}


def test_the_plugin_names_the_builds_its_pointer_chains_are_for() -> None:
    assert list(PLUGIN.builds(SETTINGS)) == ["a" * 64, "b" * 64]


def running(build: str | None) -> RunningApp:
    profile = Profile(id="app", app=App("App", 1999), match=Match((Executable("gta2.exe", ("b" * 64,)),)))
    return RunningApp(profile, ProcessInfo(42, "gta2.exe"), build)


def test_the_chain_is_picked_by_the_build_the_detector_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_hashing(pid: int) -> str:
        raise AssertionError("the executable was hashed again")

    monkeypatch.setattr(plugin, "executable_sha256", no_hashing)
    monkeypatch.setattr(plugin, "open_process_memory", lambda pid: None)

    source = plugin.create(SourceSettings("memory", "subtitles", 0.25, SETTINGS), running("b" * 64))

    assert source.name == "subtitles"


def test_without_a_build_from_the_detector_the_executable_is_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin, "executable_sha256", lambda pid: "c" * 64)

    with pytest.raises(UnsupportedAppVersion, match="c" * 64):
        plugin.create(SourceSettings("memory", "subtitles", 0.25, SETTINGS), running(None))
