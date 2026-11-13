"""The integrations of the source plugins: creating them, telling which a profile waits for, and
checking and changing their states for the API."""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from reflektortts.integrations import (
    Integration,
    IntegrationError,
    IntegrationState,
    IntegrationStatus,
    IntegrationView,
    UnknownIntegrationError,
)
from reflektortts.pipeline.plugins import SourcePlugin
from reflektortts.profiles.model import Profile

logger = logging.getLogger(__name__)

NOT_NEEDED = IntegrationState(IntegrationStatus.ENABLED)
"""How a source whose plugin offers no integration counts: as if it had one enabled."""


def load_integrations(sources: Mapping[str, SourcePlugin], folder: Path) -> dict[str, Integration]:
    """The integration of every source plugin that offers one, by the plugin's type, each given
    its own file in folder; one that cannot be created is logged and skipped."""
    integrations = {}
    for source_type, plugin in sources.items():
        if plugin.integration is None:
            continue
        try:
            integrations[source_type] = plugin.integration(folder / f"{source_type}.json")
        except Exception:
            logger.exception("The integration of the %s source is not available", source_type)
    return integrations


def missing_integrations(profile: Profile, states: Mapping[str, IntegrationState]) -> list[str]:
    """The integrations a profile is not read without, by ID: if every source of it needs one
    that is not enabled, those; else none. A source needs the integration of its type, if its
    plugin offers one (states has every integration's state)."""
    types = list(dict.fromkeys(source.type for source in profile.sources))
    if any(states.get(source_type, NOT_NEEDED).status is IntegrationStatus.ENABLED for source_type in types):
        return []
    return types


class IntegrationControl:
    """The integrations, by ID, with their states as they are now."""

    def __init__(self, integrations: Mapping[str, Integration]) -> None:
        self._integrations = integrations
        self._failing: set[str] = set()
        """Integrations whose state could not be checked, so each failure is logged once."""

    def state(self, integration_id: str) -> IntegrationState:
        """An integration's state; one that cannot be checked counts as unavailable, with the
        failure as its reason, and the failure is logged once until it can be checked again."""
        try:
            state = self._integrations[integration_id].state()
        except Exception as error:
            if integration_id not in self._failing:
                self._failing.add(integration_id)
                logger.exception("Cannot check the state of the %s integration", integration_id)
            return IntegrationState(IntegrationStatus.UNAVAILABLE, f"Could not check: {error}")
        self._failing.discard(integration_id)
        return state

    def states(self) -> dict[str, IntegrationState]:
        return {integration_id: self.state(integration_id) for integration_id in self._integrations}

    def view(self, integration_id: str) -> IntegrationView:
        integration = self._integrations[integration_id]
        return IntegrationView(integration_id, integration.name, integration.description, self.state(integration_id))

    def views(self) -> list[IntegrationView]:
        """Every integration, by ID, with its state now."""
        return [self.view(integration_id) for integration_id in sorted(self._integrations)]

    def names(self, integration_ids: Sequence[str]) -> str:
        """E.g. "the VLC integration", or "the A or the B" when either would do."""
        return " or ".join(f"the {self._integrations[integration_id].name}" for integration_id in integration_ids)

    def set_enabled(self, integration_id: str, enabled: bool) -> None:
        """Enables or disables an integration. Raises UnknownIntegrationError, or IntegrationError
        with what to do, e.g. for one that is unavailable."""
        integration = self._find(integration_id)
        if enabled:
            state = self.state(integration_id)
            if state.status is IntegrationStatus.UNAVAILABLE:
                raise IntegrationError(state.reason or f"The {integration.name} cannot be enabled now.")
            integration.enable()
        else:
            integration.disable()
        logger.info("%s the %s", "Enabled" if enabled else "Disabled", integration.name)

    def _find(self, integration_id: str) -> Integration:
        integration = self._integrations.get(integration_id)
        if integration is None:
            ids = ", ".join(sorted(self._integrations)) or "none"
            raise UnknownIntegrationError(f'There is no integration "{integration_id}". Integrations: {ids}.')
        return integration
