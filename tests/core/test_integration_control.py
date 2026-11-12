"""The integrations: creating them, and which a profile waits for."""

from dataclasses import replace
from pathlib import Path

import pytest

from reflektortts.core.integration_control import load_integrations, missing_integrations
from reflektortts.integrations import IntegrationState, IntegrationStatus
from reflektortts.pipeline.plugins import SourcePlugin
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings
from tests.core.fake_plugins import create_source
from tests.fake_integration import FakeIntegration

REMOTE = Profile(
    "remote-app-2001",
    App("Remote App", 2001),
    Match((Executable("remote.exe"),)),
    (SourceSettings("remote", "subtitles", 0.25, {}),),
)


def test_each_source_plugin_s_integration_is_created_once_with_a_file_of_its_own(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    given: list[Path] = []

    def create(path: Path) -> FakeIntegration:
        given.append(path)
        return FakeIntegration()

    def broken(path: Path) -> FakeIntegration:
        raise RuntimeError("no settings folder")

    plugins = {
        "fixed": SourcePlugin("fixed", {}, create_source),
        "remote": SourcePlugin("remote", {}, create_source, integration=create),
        "broken": SourcePlugin("broken", {}, create_source, integration=broken),
    }

    integrations = load_integrations(plugins, tmp_path / "integrations")

    assert list(integrations) == ["remote"]
    assert given == [tmp_path / "integrations" / "remote.json"]
    assert not (tmp_path / "integrations").exists()
    assert "The integration of the broken source is not available" in caplog.text


@pytest.mark.parametrize(
    ("sources", "missing"),
    [
        (("remote",), ["remote"]),
        (("remote", "remote"), ["remote"]),
        (("remote", "fixed"), []),
        (("remote", "ready"), []),
        ((), []),
    ],
)
def test_a_profile_waits_for_integrations_only_if_every_source_needs_one_not_enabled(
    sources: tuple[str, ...], missing: list[str]
) -> None:
    profile = replace(
        REMOTE, sources=tuple(SourceSettings(type, f"source {n}", 0.25, {}) for n, type in enumerate(sources))
    )
    states = {
        "remote": IntegrationState(IntegrationStatus.DISABLED),
        "ready": IntegrationState(IntegrationStatus.ENABLED),
    }

    assert missing_integrations(profile, states) == missing
