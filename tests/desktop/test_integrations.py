from typing import Any

import pytest

from reflektortts.desktop.integrations import (
    IntegrationItem,
    action,
    action_hint,
    failure_text,
    integrations_of,
    parse_integrations,
    state_text,
)
from reflektortts.desktop.profiles import parse_profiles
from tests.desktop.test_profiles import GTA2

REMOTE: dict[str, Any] = {
    "id": "remote",
    "name": "Remote integration",
    "description": "Turns on the app's remote control.",
    "state": "disabled",
    "reason": None,
}
ITEM = IntegrationItem("remote", "Remote integration", "Turns on the app's remote control.", "disabled", None)


def test_a_listing_from_the_api_becomes_items() -> None:
    assert parse_integrations({"integrations": [REMOTE]}) == [ITEM]


def test_a_profile_has_the_integrations_its_sources_need_once_each() -> None:
    sources = [
        {"name": name, "type": source_type, "stages": []}
        for name, source_type in (("a", "remote"), ("b", "memory"), ("c", "remote"))
    ]
    [profile] = parse_profiles({"profiles": [GTA2 | {"sources": sources}]})
    other = IntegrationItem("other", "Other integration", "", "enabled", None)

    assert integrations_of(profile, [other, ITEM]) == [ITEM]
    assert integrations_of(None, [ITEM]) == []


@pytest.mark.parametrize(
    ("state", "reason", "text", "button"),
    [
        ("disabled", None, "Not enabled", ("Enable", True)),
        ("enabled", None, "Enabled", ("Disable", True)),
        ("unavailable", "The app is not installed.", "Not available: The app is not installed.", ("Enable", False)),
        ("unavailable", None, "Not available", ("Enable", False)),
    ],
)
def test_the_state_and_the_button_follow_the_integration(
    state: str, reason: str | None, text: str, button: tuple[str, bool]
) -> None:
    item = IntegrationItem("remote", "Remote integration", "", state, reason)

    assert (state_text(item), action(item)) == (text, button)
    assert "the remote integration" in action_hint(item).lower()


def test_a_failed_change_is_introduced_with_the_integration_s_name() -> None:
    assert failure_text(ITEM, True) == "The Remote integration could not be enabled"
    assert failure_text(ITEM, False) == "The Remote integration could not be disabled"
