"""The end-to-end smoke test: the desktop app, run from source with per-user folders of its own,
starts, enables the VLC integration, reads the subtitle of a video a fake VLC plays through the
bundled VLC profile's stages, and notices when VLC closes; its log has no errors.

It watches ReflektorTTS only through the local API and its logs, as any client could. It writes
report.json into the output folder (folders.OUTPUT): the steps that passed and how long each
took, the one that failed and why, and what it saw. Not part of the usual test run: pytest -m e2e.
"""

import asyncio
import json
import os
import platform
import re
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any

import aiohttp
import pytest
from PIL import ImageGrab

from reflektortts.api.server import HOST
from reflektortts.desktop.system.tray_host import tray_available
from reflektortts.identity import API_PORTS, NAMES
from tests.e2e import folders
from tests.e2e.programs import free_port, port_taken, start_fake_vlc, start_reflektortts, stop, vlc_running

pytestmark = pytest.mark.e2e

PORT = API_PORTS[NAMES["e2e"]]
API = f"http://{HOST}:{PORT}/v1"
PROFILE = "vlc-media-player-2001"
SUBTITLE = "[Music] Hello from the end-to-end test."
LINE = "Hello from the end-to-end test."
"""The subtitle once the profile's stages have read it: the replace stage takes out "[Music]"."""
START_SECONDS = 120.0
"""How long ReflektorTTS gets to answer: a first start on a CI runner compiles every module."""
EVENT_SECONDS = 60.0
"""How long an expected event may take: the core looks for apps every few seconds."""
ERROR_LINE = re.compile(r"^\S+ \S+ (ERROR|CRITICAL) ", re.MULTILINE)


@dataclass
class Report:
    """report.json: shown in the E2E tests workflow's job summary."""

    system: str = f"{platform.system()} {platform.release()} ({platform.machine()})"
    python: str = platform.python_version()
    passed: list[dict[str, Any]] = field(default_factory=list)
    failed: dict[str, str] | None = None
    seen: dict[str, Any] = field(default_factory=dict)
    app_log: str = str(folders.log_folder())

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        except BaseException as error:
            self.failed = {"step": name, "error": str(error) or type(error).__name__}
            raise
        self.passed.append({"step": name, "seconds": round(time.monotonic() - start, 2)})

    def save(self) -> None:
        (folders.OUTPUT / "report.json").write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


class Events:
    """The events of the local API, in order, read on as the test waits for one."""

    def __init__(self, socket: aiohttp.ClientWebSocketResponse) -> None:
        self._socket = socket

    async def wait_for(self, description: str, wanted: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """The next event that is wanted. An error event fails the test, saying what failed."""
        async with asyncio.timeout(EVENT_SECONDS):
            async for message in self._socket:
                if message.type is not aiohttp.WSMsgType.TEXT:
                    break
                event: dict[str, Any] = json.loads(message.data)
                if event.get("type") == "error":
                    raise AssertionError(
                        f"ReflektorTTS reported an error ({event.get('kind')}): {event.get('message')}"
                    )
                if wanted(event):
                    return event
        raise AssertionError(f"The events stopped before {description}: did ReflektorTTS quit?")


def test_smoke() -> None:
    folders.clear_output()
    report = Report()
    try:
        asyncio.run(_run(report))
    except BaseException as error:
        if report.failed is None:
            report.failed = {"step": "between steps", "error": str(error) or type(error).__name__}
        raise
    finally:
        report.save()


async def _run(report: Report) -> None:
    with report.step("prepares"):
        if port_taken(PORT):
            raise AssertionError(
                f"Port {PORT} is taken, perhaps by ReflektorTTS E2E from an earlier run: quit it, then run "
                "the test again."
            )
        if vlc_running():
            raise AssertionError("VLC is running: close it, then run the test again.")
        report.seen["tray"] = tray_available()
        _write_video()
        vlc_port = free_port()
        _write_vlcrc(vlc_port)
    app = start_reflektortts(folders.OUTPUT / "reflektortts-console.log")
    try:
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            with report.step("starts"):
                await _wait_until_answering(session, app)
            with report.step("lists profiles and languages"):
                await _check_lists(session, report)
            async with session.ws_connect(f"{API}/events") as socket:
                events = Events(socket)
                with report.step("enables the VLC integration"):
                    await events.wait_for("the status sent on connecting", _is_status)
                    await _enable_integration(session, events)
                await _read_subtitles(events, vlc_port, report)
    finally:
        _screenshot(report)
        stop(app)
    with report.step("logs no errors"):
        _check_logs(report)


async def _wait_until_answering(session: aiohttp.ClientSession, app: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if app.poll() is not None:
            raise AssertionError(f"ReflektorTTS quit at start (exit code {app.returncode}): see its logs.")
        try:
            async with session.get(f"{API}/status"):
                return
        except aiohttp.ClientConnectionError:
            await asyncio.sleep(0.5)
    raise AssertionError(f"ReflektorTTS did not answer within {START_SECONDS:.0f} seconds.")


async def _check_lists(session: aiohttp.ClientSession, report: Report) -> None:
    async with session.get(f"{API}/profiles") as answer:
        profiles = {profile["id"]: profile for profile in (await answer.json())["profiles"]}
    async with session.get(f"{API}/languages") as answer:
        languages = (await answer.json())["languages"]
    report.seen["profiles"] = sorted(profiles)
    report.seen["languages"] = len(languages)
    broken = [id for id, profile in profiles.items() if profile["state"] == "broken"]
    assert not broken, f"Broken bundled profiles: {', '.join(broken)}"
    assert profiles.get(PROFILE, {}).get("state") == "not_set_up", f"{PROFILE} is not waiting for its integration"
    assert any(language["code"] == "en" for language in languages), "English is not among the languages"


async def _enable_integration(session: aiohttp.ClientSession, events: Events) -> None:
    async with session.patch(f"{API}/integrations/vlc", json={"enabled": True}) as answer:
        state = (await answer.json())["state"]
    assert state == "enabled", f"The VLC integration is {state} after enabling it"
    await events.wait_for("the status after enabling the integration", _is_status)
    async with session.get(f"{API}/profiles") as answer:
        profiles = {profile["id"]: profile for profile in (await answer.json())["profiles"]}
    state = profiles[PROFILE]["state"]
    assert state == "not_running", f"{PROFILE} is {state} once its integration is enabled, not waiting for VLC"


async def _read_subtitles(events: Events, vlc_port: int, report: Report) -> None:
    with report.step("starts VLC"):
        password = _vlcrc_value("http-password")
        vlc = start_fake_vlc(vlc_port, password, folders.MEDIA / "movie.mkv", folders.OUTPUT / "fake-vlc.log")
    try:
        with report.step("finds VLC"):
            status = await events.wait_for("VLC was found", _reading(PROFILE))
            report.seen["app"] = status["app"]
        with report.step("reads the subtitle"):
            line = await events.wait_for("a line was read", lambda event: event["type"] == "line")
            report.seen["line"] = line
            assert line["text"] == LINE, f"Read {line['text']!r}, not {LINE!r}"
            assert line["source"] == "subtitles"
    finally:
        stop(vlc)
    with report.step("notices VLC closing"):
        await events.wait_for("VLC was gone", _reading(None))


def _is_status(event: dict[str, Any]) -> bool:
    return bool(event["type"] == "status")


def _reading(profile: str | None) -> Callable[[dict[str, Any]], bool]:
    """Whether an event is a status in which the app read is one with that profile (None: no app)."""

    def wanted(event: dict[str, Any]) -> bool:
        if event["type"] != "status":
            return False
        app = event["app"]
        return app is None if profile is None else app is not None and app["profile"] == profile

    return wanted


def _write_video() -> None:
    """An empty video, which VLC never opens here, with its subtitles next to it."""
    folders.MEDIA.mkdir(parents=True)
    (folders.MEDIA / "movie.mkv").write_bytes(b"")
    (folders.MEDIA / "movie.srt").write_text(f"1\n00:00:00,000 --> 00:10:00,000\n{SUBTITLE}\n", encoding="utf-8")


def _write_vlcrc(port: int) -> None:
    """VLC's settings as a VLC that has run once leaves them, but on a port that is free."""
    path = folders.vlcrc()
    path.parent.mkdir(parents=True)
    path.write_text(f"[core]\n#extraintf=\n[http]\n#http-host=\n#http-password=\nhttp-port={port}\n", encoding="utf-8")


def _vlcrc_value(key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.*)$", folders.vlcrc().read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"VLC's settings have no {key}"
    return match.group(1)


def _check_logs(report: Report) -> None:
    """The app's log has no errors. The speech process's log is only reported: a runner may have no
    voice, or no sound device to speak on."""
    log = (folders.log_folder() / "reflektortts.log").read_text(encoding="utf-8")
    speech = folders.log_folder() / "reflektortts-tts.log"
    report.seen["speech"] = speech.read_text(encoding="utf-8").splitlines()[-5:] if speech.exists() else None
    errors = [match.group(0) + log[match.end() :].partition("\n")[0] for match in ERROR_LINE.finditer(log)]
    assert not errors, "The app logged errors:\n" + "\n".join(errors)


def _screenshot(report: Report) -> None:
    """A screenshot of the screen, on a CI runner only: on your own computer it would hold whatever else is on it."""
    if not os.environ.get("CI"):
        return
    try:
        ImageGrab.grab().save(folders.OUTPUT / "screen.png")
        report.seen["screenshot"] = "screen.png"
    except OSError as error:
        report.seen["screenshot"] = f"failed: {error}"
