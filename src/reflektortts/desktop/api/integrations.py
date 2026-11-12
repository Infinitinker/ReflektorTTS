"""What the desktop app shows of the integrations, from GET /v1/integrations: which a profile needs,
their state, and the button that enables or disables each."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from reflektortts.desktop.api.profiles import ProfileItem

ACTION_LABELS = ("Enable", "Disable")


@dataclass(frozen=True)
class IntegrationItem:
    id: str
    """The type of the source plugin that offers it, e.g. "vlc"."""
    name: str
    """Read after "the", e.g. "VLC integration"."""
    description: str
    state: str
    """As the API names it: "enabled", "disabled" or "unavailable"."""
    reason: str | None
    """Why it is unavailable; None otherwise."""


def parse_integrations(data: Mapping[str, Any]) -> list[IntegrationItem]:
    return [
        IntegrationItem(
            id=integration["id"],
            name=integration["name"],
            description=integration["description"],
            state=integration["state"],
            reason=integration["reason"],
        )
        for integration in data["integrations"]
    ]


def integrations_of(profile: ProfileItem | None, items: Sequence[IntegrationItem]) -> list[IntegrationItem]:
    """The integrations a profile's sources need, in the order of its sources."""
    if profile is None:
        return []
    by_id = {item.id: item for item in items}
    types = dict.fromkeys(source.type for source in profile.sources)
    return [by_id[source_type] for source_type in types if source_type in by_id]


def integrations_hint(items: Sequence[IntegrationItem]) -> str:
    """What the Integration… button does for a profile that needs these integrations."""
    if not items:
        return "This app needs no change in its own settings to be read."
    names = " and ".join(f"the {item.name}" for item in items)
    return f"Enable or disable {names}, which this app needs to be read."


def state_text(item: IntegrationItem) -> str:
    if item.state == "enabled":
        return "Enabled"
    if item.state == "unavailable":
        return f"Not available\n{item.reason}" if item.reason else "Not available"
    return "Not enabled"


def action(item: IntegrationItem) -> tuple[str, bool]:
    """The button's label, and whether it can be clicked: not while the integration is unavailable."""
    if item.state == "enabled":
        return ACTION_LABELS[1], True
    return ACTION_LABELS[0], item.state != "unavailable"


def failure_text(item: IntegrationItem, enabled: bool) -> str:
    """Introduces the core's message when a change fails, e.g. "The VLC integration could not be enabled"."""
    return f"The {item.name} could not be {'enabled' if enabled else 'disabled'}"
