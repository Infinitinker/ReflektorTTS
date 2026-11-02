import asyncio
import json
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import replace
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
    NoAppError,
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
    SourceStages,
    StageState,
    Status,
    SubtitleEvent,
    TextEvent,
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
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings, StageSettings
from reflektortts.tts.engine import VoiceError, VoiceInfo
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
            app=AppInfo("Grand Theft Auto 2", 42),
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

    def status(self) -> Status:
        return self.current

    def voices(self) -> list[VoiceInfo]:
        return [ADAM]

    def set_voice(self, voice: str) -> Status:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.current = replace(self.current, voice=voice)
        return self.current

    def preview_voice(self, voice: str) -> None:
        if voice != ADAM.id:
            raise VoiceError(f'There is no voice "{voice}".')
        self.previewed.append(voice)

    def set_input_language(self, language: str) -> Status:
        check_language(language)
        self.current = replace(self.current, input_language=language)
        return self.current

    def set_output_language(self, language: str) -> Status:
        check_language(language)
        self.current = replace(self.current, output_language=language)
        return self.current

    def set_ducking(self, enabled: bool, volume: float) -> Status:
        self.current = replace(self.current, ducking=enabled, duck_volume=volume)
        return self.current

    def set_speech(self, rate: float, new_line: NewLine) -> Status:
        self.current = replace(self.current, speech_rate=rate, new_line=new_line)
        return self.current

    def set_subtitles(self, enabled: bool, size: str, position: str) -> Status:
        self.current = replace(self.current, subtitles=enabled, subtitle_size=size, subtitle_position=position)
        return self.current

    def set_paused(self, paused: bool) -> Status:
        self.current = replace(self.current, paused=paused)
        return self.current

    def stop_line(self) -> Status:
        self.stopped_lines += 1
        return self.current

    def set_source_enabled(self, name: str, enabled: bool) -> Status:
        if name != "messages":
            raise SourceError(f'Grand Theft Auto 2 has no source "{name}".')
        self.current = replace(self.current, sources=(replace(self.current.sources[0], enabled=enabled),))
        return self.current

    def set_stage_enabled(self, key: str, output: Output, enabled: bool) -> Status:
        if self.current.app is None:
            raise NoAppError("No app is being read.")
        if key != TRACKER.key:
            raise StageError(f'Grand Theft Auto 2 has no stage "{key}".')
        stage = replace(TRACKER, enabled=TRACKER.enabled | {output: enabled})
        self.current = replace(self.current, sources=(replace(self.current.sources[0], stages=(stage,)),))
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

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        return self.bus.subscribe(listener)


def with_client(core: FakeCore, test: Callable[[TestClient[Any, Any]], Awaitable[None]]) -> None:
    async def run() -> None:
        async with TestClient(TestServer(create_app(core))) as client:
            await test(client)

    asyncio.run(run())


def test_status() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/status")
        assert await response.json() == {
            "type": "status",
            "app": {"title": "Grand Theft Auto 2", "pid": 42},
            "unsupported": None,
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
            "sources": [
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
            ],
        }

    with_client(FakeCore(), test)


def test_downloads_are_listed_with_their_state_and_errors() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.get("/v1/downloads", params={"refresh": "1"})
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


def test_switching_a_stage_with_no_app_being_read_is_a_conflict() -> None:
    core = FakeCore()
    core.current = replace(core.current, app=None)

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/stages", json={"key": TRACKER.key, "output": "text", "enabled": False})
        assert (response.status, await response.json()) == (409, {"error": "No app is being read."})

    with_client(core, test)


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
        assert {"code": "pl", "name": "Polski"} in languages

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


def test_changing_all_settings_together() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch(
            "/v1/settings", json={"input_language": "en", "output_language": "pl", "voice": "windows:Microsoft Adam"}
        )
        body = await response.json()
        assert (body["input_language"], body["output_language"], body["voice"]) == (
            "en",
            "pl",
            "windows:Microsoft Adam",
        )

    with_client(FakeCore(), test)


def test_ducking_can_be_changed_alone_or_with_its_level() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"duck_volume": 0.5})).json()
        assert (body["ducking"], body["duck_volume"]) == (True, 0.5)
        body = await (await client.patch("/v1/settings", json={"ducking": False})).json()
        assert (body["ducking"], body["duck_volume"]) == (False, 0.5)

    with_client(FakeCore(), test)


def test_speech_rate_and_cutting_off_can_be_changed() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"speech_rate": 1.5})).json()
        assert (body["speech_rate"], body["new_line"]) == (1.5, "wait")
        body = await (await client.patch("/v1/settings", json={"new_line": "speed_up"})).json()
        assert (body["speech_rate"], body["new_line"]) == (1.5, "speed_up")

    with_client(FakeCore(), test)


def test_subtitles_can_be_switched_on_and_set_up() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = await (await client.patch("/v1/settings", json={"subtitles": True, "subtitle_size": "large"})).json()
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
        ({"output_language": "auto"}, 'There is no language "auto". Available: en, pl.'),
        ({"input_language": "auto"}, 'There is no language "auto". Available: en, pl.'),
        ({"voice": 5}, f'"voice" cannot be set to that. {SETTINGS_HELP}'),
        ({"volume": 5, "ducking": True}, f'There is no setting "volume". {SETTINGS_HELP}'),
        ({}, SETTINGS_HELP),
        ("not json", "The request body must be a JSON object."),
    ],
)
def test_bad_settings_are_rejected_with_a_message(body: Any, message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        if isinstance(body, str):
            response = await client.patch("/v1/settings", data=body, headers={"Content-Type": "application/json"})
        else:
            response = await client.patch("/v1/settings", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_a_settings_change_with_one_bad_field_changes_nothing() -> None:
    core = FakeCore()

    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/settings", json={"ducking": False, "voice": "piper:missing"})
        assert response.status == 400

    with_client(core, test)
    assert core.current.ducking


def test_switching_a_source_off() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/sources", json={"name": "messages", "enabled": False})
        assert (await response.json())["sources"][0]["enabled"] is False

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "signs", "enabled": False}, 'Grand Theft Auto 2 has no source "signs".'),
        ({"name": "messages", "enabled": "no"}, SOURCES_HELP),
        ({"enabled": True}, SOURCES_HELP),
    ],
)
def test_bad_source_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/sources", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

    with_client(FakeCore(), test)


def test_switching_a_stage_off_for_speech() -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        body = {"key": "messages/0:tracker", "output": "speech", "enabled": False}
        response = await client.patch("/v1/stages", json=body)
        assert (await response.json())["sources"][0]["stages"][0]["enabled"] == {"text": True, "speech": False}

    with_client(FakeCore(), test)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            {"key": "messages/9:x", "output": "text", "enabled": False},
            'Grand Theft Auto 2 has no stage "messages/9:x".',
        ),
        ({"key": "messages/0:tracker", "output": "text", "enabled": "no"}, STAGES_HELP),
        ({"key": "messages/0:tracker", "output": "sound", "enabled": False}, STAGES_HELP),
        ({"key": "messages/0:tracker", "enabled": False}, STAGES_HELP),
        ({"output": "text", "enabled": True}, STAGES_HELP),
    ],
)
def test_bad_stage_requests_are_rejected_with_a_message(body: dict[str, Any], message: str) -> None:
    async def test(client: TestClient[Any, Any]) -> None:
        response = await client.patch("/v1/stages", json=body)
        assert response.status == 400
        assert await response.json() == {"error": message}

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
