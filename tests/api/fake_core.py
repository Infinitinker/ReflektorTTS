"""A fake core for the API's tests, with the views and JSON it answers with, which the other API tests share."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from reflektortts.api.routes import create_app
from reflektortts.bus import EventBus, Listener
from reflektortts.downloads.manager import Listed, Listing, State
from reflektortts.downloads.source import DownloadError, DownloadStateError, Entry, Kind, UnknownDownloadError
from reflektortts.events import (
    AppInfo,
    Output,
    ProfileSettingsView,
    SourceStages,
    StageState,
    Status,
)
from reflektortts.glossary import GlossaryTerm
from reflektortts.integrations import (
    IntegrationError,
    IntegrationState,
    IntegrationStatus,
    IntegrationView,
    UnknownIntegrationError,
)
from reflektortts.languages import check_language
from reflektortts.profiles.catalog import (
    CatalogEntry,
    Choice,
    Origin,
    ProfileChangeError,
    ProfileExistsError,
    ProfileState,
    ProfileView,
    Standing,
)
from reflektortts.profiles.errors import BrokenProfileError, SourceError, StageError, UnknownProfileError
from reflektortts.profiles.loader import ProfileError
from reflektortts.profiles.model import App, Executable, Match, Profile, Rating, SourceSettings, StageSettings
from reflektortts.settings import SettingsChange
from reflektortts.tts.engine import VoiceError, VoiceInfo, find_voice

ADAM = VoiceInfo(
    id="windows:Microsoft Adam",
    engine="windows",
    name="Microsoft Adam",
    language="pl-PL",
    engine_title="Windows",
    installed_note="Comes with Windows.",
)


MAD_MAX = CatalogEntry(
    "mad-max-2015",
    Origin.BUNDLED,
    Path("mad-max-2015.json"),
    Profile(
        "mad-max-2015",
        App("Mad Max", 2015),
        Match((Executable("MadMax.exe", ("cd71",)),)),
        (SourceSettings("avalanche", "subtitles", 0.1, {}, (StageSettings("tracker", {}),)),),
        overlay=True,
        glossary={
            "en": (GlossaryTerm("Max", keep=True, pronounce={"pl": "Maks"}),),
            "fr": (GlossaryTerm("Chumbucket", pronounce={"de": "Tschambakit", "pl": "Czambaket"}),),
        },
        rating=Rating.BRONZE,
        tested_languages=("en", "pl"),
    ),
)


GOSIA = Entry(
    "piper:pl_PL-gosia-medium",
    Kind.VOICE,
    "pl_PL-gosia-medium",
    ("pl",),
    63,
    "Dataset: CC0",
    "https://x.invalid",
    False,
    "Piper",
)


TRACKER = StageState(
    key="messages/0:tracker",
    type="tracker",
    summary="waits until a line settles",
    warning="Needed.",
    enabled={Output.TEXT: True, Output.SPEECH: True},
)


MAD_MAX_SETTINGS = ProfileSettingsView(
    profile="mad-max-2015",
    app_title="Mad Max",
    running=False,
    voice="piper:a",
    input_language="en",
    output_language="pl",
    ducking=True,
    duck_volume=0.3,
    speech_rate=1.0,
    new_line="wait",
    subtitles=False,
    subtitle_size="medium",
    subtitle_position="top",
    sources=(SourceStages("messages", "memory", True, (TRACKER,)),),
)


SETTINGS_PATH = "/v1/profiles/mad-max-2015/settings"


DISABLED = IntegrationStatus.DISABLED


class FakeCore:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.stopped_lines = 0
        self.refreshed: bool | None = None
        self.started: list[str] = []
        self.removed: list[str] = []
        self.previewed: list[str] = []
        self.switched: list[tuple[str, bool]] = []
        self.imported: list[tuple[str, bool]] = []
        self.removed_profiles: list[str] = []
        self.reloads = 0
        self.current = Status(
            app=AppInfo("Grand Theft Auto 2", 42, "grand-theft-auto-2-1999"),
            voice="piper:a",
            input_language="pl",
            output_language="en",
            paused=False,
            ducking=True,
            duck_volume=0.3,
            speech_rate=1.0,
            new_line="wait",
            subtitles=False,
            subtitle_size="medium",
            subtitle_position="top",
            sources=(SourceStages("messages", "memory", True, (TRACKER,)),),
        )
        self.view = MAD_MAX_SETTINGS
        self.changes: list[SettingsChange] = []
        self.integration = IntegrationView(
            "remote", "Remote integration", "Turns on the app's remote control.", IntegrationState(DISABLED)
        )

    def status(self) -> Status:
        return self.current

    def voices(self) -> list[VoiceInfo]:
        return [ADAM]

    def speech_rules(self) -> dict[str, tuple[str, ...]]:
        return {"pl": ("Glossary grammar", "Numbers, dates and units")}

    def preview_voice(self, voice: str) -> None:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.previewed.append(voice)

    def profile_settings(self, profile_id: str) -> ProfileSettingsView:
        self.check(profile_id)
        return self.view

    def change_profile_settings(self, profile_id: str, change: SettingsChange) -> ProfileSettingsView:
        self.check(profile_id)
        for language in (change.input_language, change.output_language):
            if language is not None:
                check_language(language)
        if change.voice is not None:
            find_voice(change.voice, self.voices())
        self.changes.append(change)
        self.view = replace(self.view, **{name: value for name, value in asdict(change).items() if value is not None})
        return self.view

    def set_source_enabled(self, profile_id: str, name: str, enabled: bool) -> ProfileSettingsView:
        self.check(profile_id)
        if name != "messages":
            raise SourceError(f'Mad Max has no source "{name}".')
        self.view = replace(self.view, sources=(replace(self.view.sources[0], enabled=enabled),))
        return self.view

    def set_stage_enabled(self, profile_id: str, key: str, output: Output, enabled: bool) -> ProfileSettingsView:
        self.check(profile_id)
        if key != TRACKER.key:
            raise StageError(f'Mad Max has no stage "{key}".')
        stage = replace(TRACKER, enabled=TRACKER.enabled | {output: enabled})
        self.view = replace(self.view, sources=(replace(self.view.sources[0], stages=(stage,)),))
        return self.view

    def check(self, profile_id: str) -> None:
        if profile_id == "broken-2000":
            raise BrokenProfileError('The profile "broken-2000" cannot be read.')
        if profile_id != MAD_MAX.id:
            raise UnknownProfileError(f'There is no profile "{profile_id}".')

    def set_paused(self, paused: bool) -> Status:
        self.current = replace(self.current, paused=paused)
        return self.current

    def stop_line(self) -> Status:
        self.stopped_lines += 1
        return self.current

    def downloads(self, refresh: bool) -> Listing:
        self.refreshed = refresh
        return Listing((Listed(GOSIA, State.AVAILABLE),), ("Could not reach the Argos list.",))

    def start_download(self, entry_id: str) -> None:
        if entry_id != GOSIA.id:
            raise DownloadError(f'There is no download "{entry_id}".')
        self.started.append(entry_id)

    def remove_download(self, entry_id: str) -> None:
        if entry_id == "piper:not-installed":
            raise DownloadStateError("not-installed is not installed.")
        if entry_id != GOSIA.id:
            raise UnknownDownloadError(f'There is no download "{entry_id}".')
        self.removed.append(entry_id)

    def profiles(self) -> list[ProfileView]:
        return [ProfileView(Choice(MAD_MAX, Standing.USED), ProfileState.NOT_RUNNING)]

    def set_profile_enabled(self, profile_id: str, enabled: bool) -> Status:
        if profile_id != MAD_MAX.id:
            raise UnknownProfileError(f'There is no profile "{profile_id}".')
        self.switched.append((profile_id, enabled))
        return self.current

    def import_profile(self, profile_id: str, data: Any, replace: bool) -> Status:
        if profile_id == "mad-max-2015" and not replace:
            raise ProfileExistsError("You already have a profile named mad-max-2015.json.")
        if not isinstance(data, dict):
            raise ProfileError(f"{profile_id}.json: must contain a JSON object.")
        self.imported.append((profile_id, replace))
        return self.current

    def copy_profile(self, profile_id: str) -> Path:
        if profile_id != MAD_MAX.id:
            raise UnknownProfileError(f'There is no profile "{profile_id}".')
        return Path("profiles") / f"{profile_id}.json"

    def remove_profile(self, profile_id: str) -> Status:
        if profile_id == "bundled-2000":
            raise ProfileChangeError("bundled-2000.json is a bundled profile, which cannot be removed.")
        if profile_id != MAD_MAX.id:
            raise UnknownProfileError(f'There is no profile "{profile_id}".')
        self.removed_profiles.append(profile_id)
        return self.current

    def reload_profiles(self) -> Status:
        self.reloads += 1
        return self.current

    def integrations(self) -> list[IntegrationView]:
        return [self.integration]

    def set_integration_enabled(self, integration_id: str, enabled: bool) -> IntegrationView:
        if integration_id != self.integration.id:
            raise UnknownIntegrationError(f'There is no integration "{integration_id}".')
        if enabled and self.integration.state.status is IntegrationStatus.UNAVAILABLE:
            raise IntegrationError("Close the app first, then try again.")
        status = IntegrationStatus.ENABLED if enabled else DISABLED
        self.integration = replace(self.integration, state=IntegrationState(status))
        return self.integration

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self.bus.subscribe(listener)


def with_client(core: FakeCore, test: Callable[[TestClient[Any, Any]], Awaitable[None]]) -> None:
    async def run() -> None:
        async with TestClient(TestServer(create_app(core))) as client:
            await test(client)

    asyncio.run(run())


SOURCES_JSON = [
    {
        "name": "messages",
        "type": "memory",
        "enabled": True,
        "stages": [
            {
                "key": "messages/0:tracker",
                "type": "tracker",
                "summary": "waits until a line settles",
                "warning": "Needed.",
                "enabled": {"text": True, "speech": True},
                "inactive": None,
            }
        ],
    }
]


MAD_MAX_SETTINGS_JSON = {
    "type": "profile_settings",
    "profile": "mad-max-2015",
    "app": {"title": "Mad Max"},
    "running": False,
    "voice": "piper:a",
    "input_language": "en",
    "output_language": "pl",
    "ducking": True,
    "duck_volume": 0.3,
    "speech_rate": 1.0,
    "new_line": "wait",
    "subtitles": False,
    "subtitle_size": "medium",
    "subtitle_position": "top",
    "sources": SOURCES_JSON,
}
