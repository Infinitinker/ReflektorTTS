"""Finding plugins through their entry points: a broken plugin is skipped and logged."""

from dataclasses import dataclass

import pytest

from reflektortts import entry_points
from reflektortts.entry_points import load_plugins


@dataclass(frozen=True)
class Plugin:
    name: str


class FakeEntryPoint:
    def __init__(self, value: str, plugin: object) -> None:
        self.value = value
        self._plugin = plugin

    def load(self) -> object:
        if isinstance(self._plugin, Exception):
            raise self._plugin
        return self._plugin


def test_a_broken_plugin_is_skipped_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    found = [
        FakeEntryPoint("good:PLUGIN", Plugin("good")),
        FakeEntryPoint("broken:PLUGIN", ImportError("No module named 'missing'")),
        FakeEntryPoint("wrong:PLUGIN", "not a plugin"),
    ]
    monkeypatch.setattr(entry_points, "entry_points", lambda group: found)

    assert load_plugins("reflektortts.test", Plugin) == [Plugin("good")]
    assert "broken:PLUGIN in reflektortts.test cannot be loaded" in caplog.text
    assert "wrong:PLUGIN in reflektortts.test is not a Plugin" in caplog.text
