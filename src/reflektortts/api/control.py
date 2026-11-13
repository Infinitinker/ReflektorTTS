"""What the local API needs from the core: the CoreControl protocol, which the core implements."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from reflektortts.bus import Listener
from reflektortts.downloads.manager import Listing
from reflektortts.events import Output, ProfileSettingsView, Status
from reflektortts.integrations import IntegrationView
from reflektortts.profiles.catalog import ProfileView
from reflektortts.settings import SettingsChange
from reflektortts.tts.engine import VoiceInfo


class CoreControl(Protocol):
    """What the API needs from the core. Every method on a profile's settings raises
    UnknownProfileError if there is no such profile, and BrokenProfileError if its file cannot be
    read."""

    def status(self) -> Status: ...

    def voices(self) -> list[VoiceInfo]: ...

    def speech_rules(self) -> Mapping[str, tuple[str, ...]]:
        """The speech rules of the installed stages that each output language has, by its code."""
        ...

    def preview_voice(self, voice: str) -> None:
        """Raises VoiceError if the voice is not available or speaks no supported language."""

    def profile_settings(self, profile_id: str) -> ProfileSettingsView: ...

    def change_profile_settings(self, profile_id: str, change: SettingsChange) -> ProfileSettingsView:
        """Raises LanguageError for a language that is not supported, VoiceError for a voice that is
        not available; then nothing is changed."""

    def set_source_enabled(self, profile_id: str, name: str, enabled: bool) -> ProfileSettingsView:
        """Raises SourceError if the profile has no such source."""

    def set_stage_enabled(self, profile_id: str, key: str, output: Output, enabled: bool) -> ProfileSettingsView:
        """Raises StageError if the profile has no such stage."""

    def set_paused(self, paused: bool) -> Status: ...

    def stop_line(self) -> Status: ...

    def profiles(self) -> list[ProfileView]: ...

    def set_profile_enabled(self, profile_id: str, enabled: bool) -> Status:
        """Raises UnknownProfileError if there is no such profile."""

    def import_profile(self, profile_id: str, data: Any, replace: bool) -> Status:
        """Raises ProfileError, ProfileExistsError or ProfileChangeError."""

    def copy_profile(self, profile_id: str) -> Path:
        """Raises UnknownProfileError or ProfileChangeError."""

    def remove_profile(self, profile_id: str) -> Status:
        """Raises UnknownProfileError or ProfileChangeError."""

    def reload_profiles(self) -> Status: ...

    def integrations(self) -> list[IntegrationView]: ...

    def set_integration_enabled(self, integration_id: str, enabled: bool) -> IntegrationView:
        """Raises UnknownIntegrationError if there is no such integration, IntegrationError if it
        cannot be done now."""

    def downloads(self, refresh: bool) -> Listing:
        """refresh fetches the lists from the internet, so it can take a while."""

    def start_download(self, entry_id: str) -> None:
        """Raises DownloadError if it cannot start."""

    def remove_download(self, entry_id: str) -> None:
        """Raises DownloadError if it cannot be removed."""

    def subscribe(self, listener: Listener) -> Callable[[], None]: ...
