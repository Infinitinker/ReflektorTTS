from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.replace import PLUGIN


def test_rules_apply_in_order_and_surrounding_spaces_are_trimmed() -> None:
    stage = PLUGIN.create({"rules": [{"find": "#", "replace": ""}, {"find": "ya", "replace": "you"}]})

    event = stage.process(TextEvent("memory", "#Welcome to the #Downtown District#, ya bum #", 1.0))

    assert event == TextEvent("memory", "Welcome to the Downtown District, you bum", 1.0)


def test_plugin_is_registered() -> None:
    assert stage_plugins()["replace"] is PLUGIN
