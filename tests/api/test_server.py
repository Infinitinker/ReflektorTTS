import asyncio
import json
import threading
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from reflektortts.api.server import (
    SETTINGS_HELP,
    SOURCES_HELP,
    STAGES_HELP,
    ApiError,
    ApiServer,
    BrokenProfileError,
    SourceError,
    StageError,
    UnknownProfileError,
    create_app,
)
from reflektortts.bus import EventBus, Listener
from reflektortts.downloads.manager import Listed, Listing, State
from reflektortts.downloads.source import DownloadError, DownloadStateError, Entry, Kind, UnknownDownloadError
from reflektortts.events import (
    AppInfo,
    DownloadEvent,
    ErrorEvent,
    Output,
    ProfileSettingsView,
    SourceStages,
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
)
from reflektortts.integrations import (
    IntegrationError,
    IntegrationState,
    IntegrationStatus,
    IntegrationView,
    UnknownIntegrationError,
)
from reflektortts.languages import LanguageError, check_language
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
from reflektortts.profiles.loader import ProfileError
from reflektortts.profiles.model import App, Executable, Match, Profile, Rating, SourceSettings, StageSettings
from reflektortts.settings import SettingsChange
from reflektortts.tts.engine import VoiceError, VoiceInfo, find_voice
from reflektortts.tts.service import NewLine

ADAM = VoiceInfo(
    id="windows:Microsoft Adam", engine="windows", name="Microsoft Adam", language="pl-PL", engine_title="Windows"
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
        rating=Rating.BRONZE,
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


def test_status() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/status")
        assert await response.json() == {
            "type": "status",
            "app": {"title": "Grand Theft Auto 2", "pid": 42, "profile": "grand-theft-auto-2-1999"},
            "unsupported": None,
            "source_error": None,
            "voice": "piper:a",
            "input_language": "pl",
            "output_language": "en",
            "paused": False,
            "ducking": True,
            "duck_volume": 0.3,
            "speech_rate": 1.0,
            "new_line": "wait",
            "subtitles": False,
            "subtitle_size": "medium",
            "subtitle_position": "top",
            "sources": SOURCES_JSON,
        }

    with_client(FakeCore(), test)


def test_the_status_gives_the_last_source_error_of_the_app_being_read() -> None:
    core = FakeCore()
    core.current = replace(core.current, source_error=ErrorEvent("source.error", "messages", "Cannot read."))

    async def test(client: TestClient[Any, Any]) -> None:
        status = await (await client.get("/v1/status")).json()
        assert status["source_error"] == {"source": "messages", "message": "Cannot read."}

    with_client(core, test)


def test_a_profile_s_settings_are_shown_by_its_id() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get(SETTINGS_PATH)
        assert (response.status, await response.json()) == (200, MAD_MAX_SETTINGS_JSON)
        unknown = await client.get("/v1/profiles/nope/settings")
        assert (unknown.status, await unknown.json()) == (404, {"error": 'There is no profile "nope".'})
        broken = await client.get("/v1/profiles/broken-2000/settings")
        assert (broken.status, await broken.json()) == (409, {"error": 'The profile "broken-2000" cannot be read.'})

    with_client(FakeCore(), test)


def test_a_profile_s_settings_come_as_events_when_they_change() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        async with client.ws_connect("/v1/events") as socket:
            await socket.receive_json()  # The status first.
            core.bus.publish(MAD_MAX_SETTINGS)
            assert await socket.receive_json() == MAD_MAX_SETTINGS_JSON

    with_client(core, test)


def test_downloads_are_listed_with_their_state_and_errors() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.post("/v1/downloads/refresh")
        assert await response.json() == {
            "entries": [
                {
                    "id": "piper:pl_PL-gosia-medium",
                    "source_title": "Piper",
                    "kind": "voice",
                    "name": "pl_PL-gosia-medium",
                    "languages": ["pl"],
                    "size": 63,
                    "license": "Dataset: CC0",
                    "page": "https://x.invalid",
                    "state": "available",
                    "done": 0,
                    "total": None,
                }
            ],
            "errors": ["Could not reach the Argos list."],
        }

    with_client(core, test)
    assert core.refreshed is True


def test_listing_downloads_with_a_get_never_fetches_the_lists() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await client.get("/v1/downloads", params={"refresh": "1"})).status == 200

    with_client(core, test)
    assert core.refreshed is False


def test_a_core_that_holds_its_lock_does_not_stall_other_requests() -> None:
    core = FakeCore()
    release = threading.Event()

    def slow_stop_line() -> Status:
        release.wait(timeout=5)
        return core.current

    core.stop_line = slow_stop_line  # type: ignore[method-assign]

    async def test(client: TestClient[Any, Any]) -> None:
        stopping = asyncio.create_task(client.post("/v1/stop"))
        await asyncio.sleep(0.1)
        assert (await client.get("/v1/languages")).status == 200
        assert not stopping.done()
        release.set()
        assert (await stopping).status == 200

    with_client(core, test)


def test_a_download_is_started_and_removed_by_id() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        started = await client.post("/v1/downloads", json={"id": GOSIA.id})
        assert started.status == 202
        assert (await client.delete(f"/v1/downloads/{GOSIA.id}")).status == 200
        unknown = await client.post("/v1/downloads", json={"id": "piper:x"})
        assert (unknown.status, (await unknown.json())["error"]) == (400, 'There is no download "piper:x".')
        assert (await client.post("/v1/downloads", json={})).status == 400
        missing = await client.delete("/v1/downloads/piper:x")
        assert (missing.status, (await missing.json())["error"]) == (404, 'There is no download "piper:x".')
        assert (await client.delete("/v1/downloads/piper:not-installed")).status == 409

    with_client(core, test)
    assert core.started == core.removed == [GOSIA.id]


def test_a_voice_is_previewed_by_id() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await client.post("/v1/voices/preview", json={"voice": ADAM.id})).status == 202
        unknown = await client.post("/v1/voices/preview", json={"voice": "piper:x"})
        assert (unknown.status, (await unknown.json())["error"]) == (400, 'There is no voice "piper:x".')
        assert (await client.post("/v1/voices/preview", json={})).status == 400

    with_client(core, test)
    assert core.previewed == [ADAM.id]


def test_download_progress_comes_as_events() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        async with client.ws_connect("/v1/events") as socket:
            await socket.receive_json()  # The status first.
            core.bus.publish(DownloadEvent(GOSIA.id, "downloading", 30, 63))
            assert await socket.receive_json() == {
                "type": "download",
                "id": GOSIA.id,
                "state": "downloading",
                "done": 30,
                "total": 63,
                "message": "",
            }

    with_client(core, test)


def test_languages() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        languages = (await (await client.get("/v1/languages")).json())["languages"]
        assert {"code": "pl", "name": "Polski", "english_name": "Polish"} in languages
        english_names = [language["english_name"] for language in languages]
        assert english_names == sorted(english_names)

    with_client(FakeCore(), test)


def test_voices() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/voices")
        assert await response.json() == {
            "voices": [
                {
                    "id": "windows:Microsoft Adam",
                    "engine": "windows",
                    "name": "Microsoft Adam",
                    "language": "pl-PL",
                    "engine_title": "Windows",
                }
            ]
        }

    with_client(FakeCore(), test)


def test_changing_all_settings_together_is_one_change() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        body = {"input_language": "pl", "output_language": "en", "voice": "windows:Microsoft Adam", "speech_rate": 2}
        response = await client.patch(SETTINGS_PATH, json=body)
        answer = await response.json()
        assert response.status == 200
        assert (answer["type"], answer["input_language"], answer["output_language"], answer["voice"]) == (
            "profile_settings",
            "pl",
            "en",
            "windows:Microsoft Adam",
        )

    with_client(core, test)
    assert core.changes == [
        SettingsChange(voice="windows:Microsoft Adam", input_language="pl", output_language="en", speech_rate=2.0)
    ]


def test_ducking_can_be_changed_alone_or_with_its_level() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch(SETTINGS_PATH, json={"duck_volume": 0.5})).json()
        assert (body["ducking"], body["duck_volume"]) == (True, 0.5)
        body = await (await client.patch(SETTINGS_PATH, json={"ducking": False})).json()
        assert (body["ducking"], body["duck_volume"]) == (False, 0.5)

    with_client(FakeCore(), test)


def test_speech_rate_and_cutting_off_can_be_changed() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch(SETTINGS_PATH, json={"speech_rate": 1.5})).json()
        assert (body["speech_rate"], body["new_line"]) == (1.5, "wait")
        body = await (await client.patch(SETTINGS_PATH, json={"new_line": "speed_up"})).json()
        assert (body["speech_rate"], body["new_line"]) == (1.5, "speed_up")

    with_client(core, test)
    assert core.changes[-1].new_line is NewLine.SPEED_UP


def test_subtitles_can_be_switched_on_and_set_up() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch(SETTINGS_PATH, json={"subtitles": True, "subtitle_size": "large"})).json()
        assert (body["subtitles"], body["subtitle_size"], body["subtitle_position"]) == (True, "large", "top")

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"voice": "piper:missing"}, 'There is no voice "piper:missing". Available: windows:Microsoft Adam.'),
        ({"subtitle_size": "huge"}, f'"subtitle_size" cannot be set to that. {SETTINGS_HELP}'),
        ({"speech_rate": 3}, f'"speech_rate" cannot be set to that. {SETTINGS_HELP}'),
        ({"new_line": "skip"}, f'"new_line" cannot be set to that. {SETTINGS_HELP}'),
        ({"subtitle_position": "left"}, f'"subtitle_position" cannot be set to that. {SETTINGS_HELP}'),
        ({"subtitles": 1}, f'"subtitles" cannot be set to that. {SETTINGS_HELP}'),
        ({"ducking": "yes"}, f'"ducking" cannot be set to that. {SETTINGS_HELP}'),
        ({"duck_volume": 1.5}, f'"duck_volume" cannot be set to that. {SETTINGS_HELP}'),
        ({"duck_volume": True}, f'"duck_volume" cannot be set to that. {SETTINGS_HELP}'),
        ({"output_language": "auto"}, 'There is no language "auto": use its two-letter ISO 639-1 code, such as "en".'),
        ({"input_language": "auto"}, 'There is no language "auto": use its two-letter ISO 639-1 code, such as "en".'),
        ({"voice": 5}, f'"voice" cannot be set to that. {SETTINGS_HELP}'),
        ({"volume": 5, "ducking": True}, f'There is no setting "volume". {SETTINGS_HELP}'),
        ({}, SETTINGS_HELP),
        ("not json", "The request body must be a JSON object."),
    ],
)
def test_bad_settings_are_rejected_with_a_message(body: Any, message: str) -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        if isinstance(body, str):
            response = await client.patch(SETTINGS_PATH, data=body, headers={"Content-Type": "application/json"})
        else:
            response = await client.patch(SETTINGS_PATH, json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(core, test)
    assert core.changes == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("settings", {"ducking": False}),
        ("sources", {"name": "messages", "enabled": False}),
        ("stages", {"key": TRACKER.key, "output": "text", "enabled": False}),
    ],
)
def test_changing_an_unknown_or_broken_profile_is_refused(path: str, body: dict[str, Any]) -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        unknown = await client.patch(f"/v1/profiles/nope/{path}", json=body)
        assert (unknown.status, await unknown.json()) == (404, {"error": 'There is no profile "nope".'})
        broken = await client.patch(f"/v1/profiles/broken-2000/{path}", json=body)
        assert broken.status == 409

    with_client(core, test)
    assert core.view == MAD_MAX_SETTINGS


def test_switching_a_source_off() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/profiles/mad-max-2015/sources", json={"name": "messages", "enabled": False})
        answer = await response.json()
        assert (answer["type"], answer["sources"][0]["enabled"]) == ("profile_settings", False)

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "signs", "enabled": False}, 'Mad Max has no source "signs".'),
        ({"name": "messages", "enabled": "no"}, SOURCES_HELP),
        ({"enabled": True}, SOURCES_HELP),
    ],
)
def test_bad_source_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/profiles/mad-max-2015/sources", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_switching_a_stage_off_for_speech() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = {"key": "messages/0:tracker", "output": "speech", "enabled": False}
        response = await client.patch("/v1/profiles/mad-max-2015/stages", json=body)
        assert (await response.json())["sources"][0]["stages"][0]["enabled"] == {"text": True, "speech": False}

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"key": "messages/9:x", "output": "text", "enabled": False}, 'Mad Max has no stage "messages/9:x".'),
        ({"key": "messages/0:tracker", "output": "text", "enabled": "no"}, STAGES_HELP),
        ({"key": "messages/0:tracker", "output": "sound", "enabled": False}, STAGES_HELP),
        ({"key": "messages/0:tracker", "enabled": False}, STAGES_HELP),
        ({"output": "text", "enabled": True}, STAGES_HELP),
    ],
)
def test_bad_stage_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/profiles/mad-max-2015/stages", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


@pytest.mark.parametrize("path", ["/v1/settings", "/v1/sources", "/v1/stages"])
def test_the_routes_for_only_the_app_being_read_are_gone(path: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        assert (await client.patch(path, json={"ducking": False})).status == 404

    with_client(FakeCore(), test)


def test_pause_resume_and_stop_line() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        assert (await (await client.post("/v1/pause")).json())["paused"] is True
        assert (await (await client.post("/v1/resume")).json())["paused"] is False
        assert (await client.post("/v1/stop")).status == 200

    with_client(core, test)
    assert core.stopped_lines == 1


def test_events_start_with_the_status_then_follow_the_core() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        socket = await client.ws_connect("/v1/events")
        first = await socket.receive_json(timeout=2)
        core.bus.publish(TextEvent("messages", "Welcome to Downtown", 1.0))
        core.bus.publish(SubtitleEvent("Witamy w Downtown"))
        core.bus.publish(ErrorEvent("source.error", "messages", "app closed"))
        line = await socket.receive_json(timeout=2)
        subtitle = await socket.receive_json(timeout=2)
        error = await socket.receive_json(timeout=2)
        await socket.close()

        assert first["type"] == "status"
        assert line == {"type": "line", "source": "messages", "text": "Welcome to Downtown"}
        assert subtitle == {"type": "subtitle", "text": "Witamy w Downtown"}
        assert error == {"type": "error", "kind": "source.error", "origin": "messages", "message": "app closed"}

    with_client(core, test)


def test_server_runs_on_its_own_thread_and_reports_a_busy_port() -> None:
    server = ApiServer(FakeCore(), port=0)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/v1/status", timeout=5) as response:
            assert json.load(response)["voice"] == "piper:a"

        second = ApiServer(FakeCore(), port=server.port)
        with pytest.raises(ApiError, match="Is ReflektorTTS already running"):
            second.start()
        time.sleep(0.5)  # Lets the failed server's loop close, as when the app is slow to stop it.
        second.stop()
    finally:
        server.stop()


def test_language_errors_are_language_errors() -> None:
    with pytest.raises(LanguageError):
        check_language("auto")


def test_profiles_are_listed_and_switched() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        listed = await (await client.get("/v1/profiles")).json()
        assert listed == {
            "profiles": [
                {
                    "id": "mad-max-2015",
                    "title": "Mad Max",
                    "year": 2015,
                    "origin": "bundled",
                    "state": "not_running",
                    "reason": None,
                    "file": str(Path("mad-max-2015.json")),
                    "overlay": True,
                    "rating": "bronze",
                    "executables": [{"name": "MadMax.exe", "sha256": ["cd71"]}],
                    "sources": [{"name": "subtitles", "type": "avalanche", "stages": ["tracker"]}],
                }
            ]
        }
        assert (await client.patch("/v1/profiles", json={"id": "mad-max-2015", "enabled": False})).status == 200
        unknown = await client.patch("/v1/profiles", json={"id": "nope", "enabled": False})
        assert (unknown.status, (await unknown.json())["error"]) == (400, 'There is no profile "nope".')
        assert (await client.patch("/v1/profiles", json={"id": "mad-max-2015"})).status == 400

    with_client(core, test)
    assert core.switched == [("mad-max-2015", False)]


def test_profiles_are_imported_copied_removed_and_reloaded() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        added = await client.post("/v1/profiles", json={"id": "mine-2000", "profile": {"version": 1}})
        assert added.status == 200
        exists = await client.post("/v1/profiles", json={"id": "mad-max-2015", "profile": {}})
        assert exists.status == 409
        replaced = await client.post("/v1/profiles", json={"id": "mad-max-2015", "profile": {}, "replace": True})
        assert replaced.status == 200
        broken = await client.post("/v1/profiles", json={"id": "mine-2000", "profile": []})
        assert (broken.status, (await broken.json())["error"]) == (400, "mine-2000.json: must contain a JSON object.")
        assert (await client.post("/v1/profiles", json={"id": "mine-2000"})).status == 400

        copied = await client.post("/v1/profiles/mad-max-2015/copy")
        assert (copied.status, await copied.json()) == (200, {"file": str(Path("profiles") / "mad-max-2015.json")})
        assert (await client.post("/v1/profiles/nope/copy")).status == 404

        assert (await client.delete("/v1/profiles/mad-max-2015")).status == 200
        assert (await client.delete("/v1/profiles/nope")).status == 404
        assert (await client.delete("/v1/profiles/bundled-2000")).status == 409
        assert (await client.post("/v1/profiles/reload")).status == 200

    with_client(core, test)
    assert core.imported == [("mine-2000", False), ("mad-max-2015", True)]
    assert core.removed_profiles == ["mad-max-2015"]
    assert core.reloads == 1


def test_integrations_are_listed_with_their_state() -> None:
    core = FakeCore()
    core.integration = replace(
        core.integration, state=IntegrationState(IntegrationStatus.UNAVAILABLE, "The app is not installed.")
    )

    async def test(client: TestClient[Any, Any]) -> None:
        listed = await client.get("/v1/integrations")
        assert (listed.status, await listed.json()) == (
            200,
            {
                "integrations": [
                    {
                        "id": "remote",
                        "name": "Remote integration",
                        "description": "Turns on the app's remote control.",
                        "state": "unavailable",
                        "reason": "The app is not installed.",
                    }
                ]
            },
        )

    with_client(core, test)


def test_an_integration_is_enabled_and_disabled_by_id() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        enabled = await client.patch("/v1/integrations/remote", json={"enabled": True})
        assert (enabled.status, (await enabled.json())["state"]) == (200, "enabled")
        disabled = await client.patch("/v1/integrations/remote", json={"enabled": False})
        assert (disabled.status, await disabled.json()) == (
            200,
            {
                "id": "remote",
                "name": "Remote integration",
                "description": "Turns on the app's remote control.",
                "state": "disabled",
                "reason": None,
            },
        )

    with_client(core, test)


@pytest.mark.parametrize("body", [{}, {"enabled": "yes"}, []])
def test_bad_integration_requests_are_rejected_with_a_message(body: Any) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/integrations/remote", json=body)
        assert (response.status, await response.json()) == (400, {"error": 'Send {"enabled": true or false}.'})

    with_client(FakeCore(), test)


def test_an_unknown_integration_or_one_that_cannot_change_now_is_refused() -> None:
    core = FakeCore()
    core.integration = replace(core.integration, state=IntegrationState(IntegrationStatus.UNAVAILABLE, "Not now."))

    async def test(client: TestClient[Any, Any]) -> None:
        unknown = await client.patch("/v1/integrations/nope", json={"enabled": True})
        assert (unknown.status, await unknown.json()) == (404, {"error": 'There is no integration "nope".'})
        refused = await client.patch("/v1/integrations/remote", json={"enabled": True})
        assert (refused.status, await refused.json()) == (409, {"error": "Close the app first, then try again."})

    with_client(core, test)
