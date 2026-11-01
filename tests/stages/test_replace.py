import json
from pathlib import Path

import pytest

from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.profiles.loader import PluginSchemas, ProfileError, load_profile
from reflektortts.stages.replace import PLUGIN


def run(rules: list[dict[str, str]], text: str) -> str:
    event = PLUGIN.create({"rules": rules}).process(TextEvent("memory", text, 1.0))
    assert event is not None
    return event.text


def test_literal_rules_apply_in_order_and_surrounding_spaces_are_trimmed() -> None:
    rules = [{"find": "#", "replace": ""}, {"find": "ya", "replace": "you"}]

    assert run(rules, "#Welcome to the #Downtown District#, ya bum #") == "Welcome to the Downtown District, you bum"


def test_literal_rules_take_special_characters_literally() -> None:
    assert run([{"find": "$1.0", "replace": "\\1 dollar"}], "Costs $1.0 now") == "Costs \\1 dollar now"


def test_pattern_rules_use_groups() -> None:
    rules = [{"pattern": "#([^#]*)#", "replace": "\\1"}]

    assert run(rules, "Hello #TEST# and #MORE#") == "Hello TEST and MORE"


def test_plugin_is_registered() -> None:
    assert stage_plugins()["replace"] is PLUGIN


def write_profile(tmp_path: Path, rule: dict[str, str]) -> Path:
    path = tmp_path / "game.json"
    profile = {
        "version": 2,
        "game": {"title": "Game", "year": 2000},
        "match": {"executables": [{"name": "game.exe"}]},
        "sources": [{"type": "fixed", "name": "text", "stages": [{"type": "replace", "rules": [rule]}]}],
    }
    path.write_text(json.dumps(profile), "utf-8")
    return path


SCHEMAS = PluginSchemas(sources={"fixed": {"type": "object"}}, stages={"replace": PLUGIN.settings_schema})


def test_invalid_pattern_is_rejected_when_the_profile_loads(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"\$\.sources\[0\]\.stages\[0\]\.rules\[0\]"):
        load_profile(write_profile(tmp_path, {"pattern": "#([^#]*#", "replace": "\\1"}), SCHEMAS)


def test_a_rule_cannot_have_both_find_and_pattern(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"rules\[0\]"):
        load_profile(write_profile(tmp_path, {"find": "#", "pattern": "#", "replace": ""}), SCHEMAS)
