"""Which profiles are used, and what each is doing: read, waiting for its app or an integration,
or set aside, and why."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from reflektortts.core.integration_control import missing_integrations
from reflektortts.integrations import IntegrationState
from reflektortts.profiles.catalog import Choice, ProfileState, ProfileView, Standing
from reflektortts.profiles.model import Profile


def used_profiles(choices: Sequence[Choice], integrations: Mapping[str, IntegrationState]) -> list[Profile]:
    """The profiles whose apps are read: used, and set up."""
    return [
        choice.entry.profile
        for choice in choices
        if choice.entry.profile
        and choice.standing == Standing.USED
        and not missing_integrations(choice.entry.profile, integrations)
    ]


def profile_state(
    choice: Choice, integrations: Mapping[str, IntegrationState], read: str | None, unsupported: str | None
) -> ProfileState:
    """read and unsupported are the IDs of the profile being read and of one whose app runs in a
    build it does not support, if any."""
    if choice.standing != Standing.USED:
        return ProfileState(choice.standing.value)
    if read == choice.entry.id:
        return ProfileState.READING
    if choice.entry.profile is not None and missing_integrations(choice.entry.profile, integrations):
        return ProfileState.NOT_SET_UP
    if unsupported == choice.entry.id:
        return ProfileState.UNSUPPORTED
    return ProfileState.NOT_RUNNING


def profile_views(
    choices: Sequence[Choice],
    integrations: Mapping[str, IntegrationState],
    read: str | None,
    unsupported: str | None,
    integration_names: Callable[[Sequence[str]], str],
) -> list[ProfileView]:
    """Every profile, with why it is not used or what its app is doing; see profile_state.
    integration_names names the integrations a profile waits for, e.g. "the VLC integration"."""
    views = []
    for choice in choices:
        state = profile_state(choice, integrations, read, unsupported)
        if state is ProfileState.NOT_SET_UP and choice.entry.profile is not None:
            missing = missing_integrations(choice.entry.profile, integrations)
            choice = replace(choice, reason=f"Not read until {integration_names(missing)} is enabled.")
        views.append(ProfileView(choice, state))
    return views
