from reflektortts.pipeline.plugins import source_plugins
from reflektortts.sources.memory.plugin import PLUGIN, parse_settings
from reflektortts.sources.memory.pointer import Address
from reflektortts.sources.memory.source import MemorySettings, PointerChain


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
