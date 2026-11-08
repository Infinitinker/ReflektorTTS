import sys
from pathlib import Path

import pytest

from reflektortts.apps.detector import ProcessInfo, RunningApp
from reflektortts.apps.executable import ExecutableError
from reflektortts.pipeline.plugins import source_plugins
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings
from reflektortts.sources.vlc import plugin
from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.integration import VlcIntegration
from reflektortts.sources.vlc.plugin import PLUGIN

VLC = RunningApp(
    Profile(id="vlc-media-player-2001", app=App("VLC media player", 2001), match=Match((Executable("vlc.exe"),))),
    ProcessInfo(42, "vlc.exe"),
)
SETTINGS = SourceSettings("vlc", "subtitles", 0.2, {})


def test_vlc_plugin_is_registered_through_entry_points() -> None:
    assert source_plugins()["vlc"] is PLUGIN


def test_the_plugin_offers_the_vlc_integration_without_touching_files(tmp_path: Path) -> None:
    assert PLUGIN.integration is not None

    integration = PLUGIN.integration(tmp_path / "integrations" / "vlc.json")

    assert isinstance(integration, VlcIntegration)
    assert integration.name == "VLC integration"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="VLC is portable only on Windows")
def test_a_portable_vlc_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "portable").mkdir()
    monkeypatch.setattr(plugin, "executable_path", lambda pid: tmp_path / "vlc.exe")

    with pytest.raises(VlcError, match="This VLC is a portable copy"):
        plugin.create(SETTINGS, VLC)


def test_an_installed_vlc_gets_a_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(plugin, "executable_path", lambda pid: tmp_path / "vlc.exe")
    monkeypatch.setattr(plugin, "vlcrc_path", lambda: tmp_path / "vlcrc")

    source = plugin.create(SETTINGS, VLC)

    assert (source.name, source.poll_interval) == ("subtitles", 0.2)


def test_a_vlc_whose_files_cannot_be_found_counts_as_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_files(pid: int) -> Path:
        raise ExecutableError("Cannot find the program's files: access denied")

    monkeypatch.setattr(plugin, "executable_path", no_files)

    assert plugin.portable_folder(42) is None
