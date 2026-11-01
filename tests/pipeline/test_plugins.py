from collections.abc import Mapping
from typing import Any

from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import StagePlugin, inactive_reason
from reflektortts.pipeline.protocols import Stage


def create(settings: Mapping[str, Any]) -> Stage:
    raise AssertionError("not created in these tests")


def failing_check(languages: Languages) -> str | None:
    raise KeyError("pl")


def test_a_stage_that_cannot_check_its_languages_counts_as_inactive() -> None:
    plugin = StagePlugin("broken", {}, create, inactive_reason=failing_check)

    assert inactive_reason(plugin, Languages("en", "pl")) == "Could not check: 'pl'"


def test_a_stage_that_works_with_the_languages_is_active() -> None:
    plugin = StagePlugin("fine", {}, create)

    assert inactive_reason(plugin, Languages("en", "pl")) is None
