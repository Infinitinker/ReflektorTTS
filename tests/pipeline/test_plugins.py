"""The plugin registry: whether a stage is active for the languages, and plugins skipped for a bad schema or type."""

from collections.abc import Mapping
from typing import Any

import pytest

from reflektortts.glossary import Glossaries
from reflektortts.languages import Languages
from reflektortts.pipeline import plugins
from reflektortts.pipeline.plugins import StagePlugin, inactive_reason, stage_plugins
from reflektortts.pipeline.protocols import Stage


def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Stage:
    raise AssertionError("not created in these tests")


def failing_check(languages: Languages) -> str | None:
    raise KeyError("pl")


def test_a_stage_that_cannot_check_its_languages_counts_as_inactive() -> None:
    plugin = StagePlugin("broken", {}, create, inactive_reason=failing_check)

    assert inactive_reason(plugin, Languages("en", "pl")) == "Could not check: 'pl'"


def test_a_stage_that_works_with_the_languages_is_active() -> None:
    plugin = StagePlugin("fine", {}, create)

    assert inactive_reason(plugin, Languages("en", "pl")) is None


def test_a_plugin_with_an_invalid_settings_schema_is_skipped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fine = StagePlugin("fine", {"type": "object"}, create)
    broken = StagePlugin("broken", {"type": "text"}, create)
    monkeypatch.setattr(plugins, "load_plugins", lambda group, kind: [fine, broken])

    assert stage_plugins() == {"fine": fine}
    assert "The plugin broken has an invalid settings schema" in caplog.text


def test_of_two_plugins_with_one_type_the_first_is_kept_and_both_are_named(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def community_create(settings: Mapping[str, Any], glossaries: Glossaries) -> Stage:
        raise AssertionError("not created in these tests")

    community_create.__module__ = "community.plugin"
    built_in = StagePlugin("tracker", {"type": "object"}, create)
    community = StagePlugin("tracker", {"type": "object"}, community_create)
    monkeypatch.setattr(plugins, "load_plugins", lambda group, kind: [built_in, community])

    assert stage_plugins() == {"tracker": built_in}
    assert (
        f"The plugins {__name__} and community.plugin in reflektortts.stages both have the type tracker" in caplog.text
    )
