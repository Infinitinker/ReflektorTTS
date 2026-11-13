"""Integrations: changes a source needs made in the app's own settings before it can read anything,
which the user enables and disables from a ReflektorTTS window.

A source plugin offers one through SourcePlugin.integration; its ID is the plugin's type. A profile
whose sources all need an integration that is not enabled is not read, and shows as not set up.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class IntegrationError(Exception):
    """An integration cannot be enabled or disabled now; the message is shown to the user as it is,
    e.g. "Close VLC first, then try again"."""


class UnknownIntegrationError(Exception):
    """There is no integration with that ID."""


class IntegrationStatus(StrEnum):
    ENABLED = "enabled"
    """The app is set up: its sources can read it."""
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    """It cannot be enabled now, e.g. the app is not installed; the state's reason says why."""


@dataclass(frozen=True)
class IntegrationState:
    status: IntegrationStatus
    reason: str | None = None
    """Why it is unavailable, for the user, e.g. "VLC's settings file was not found"; None otherwise."""


class Integration(Protocol):
    """What a source plugin's integration does. Its methods are called under the core's lock, so
    keep them quick, and they never run at the same time."""

    name: str
    """What the user calls it, read after "the", e.g. "VLC integration"; titles its group in the
    ReflektorTTS window's Profiles tab."""
    description: str
    """What enabling it changes and what disabling it puts back, in a sentence or two for the user."""

    def state(self) -> IntegrationState:
        """Checks the app's settings each time it is called: the user can change them outside
        ReflektorTTS."""
        ...

    def enable(self) -> None:
        """Makes the changes the source needs. Raises IntegrationError with what to do, e.g. when
        the app must be closed first."""
        ...

    def disable(self) -> None:
        """Puts back what enable changed, leaving alone what the user changed since. Raises
        IntegrationError with what to do."""
        ...


@dataclass(frozen=True)
class IntegrationView:
    """An integration as the API shows it."""

    id: str
    """The type of the source plugin that offers it, e.g. "vlc"."""
    name: str
    description: str
    state: IntegrationState
