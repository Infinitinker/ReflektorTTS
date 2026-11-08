"""Registers the VLC source: its settings schema, how to create it for a running VLC, and the
integration that turns VLC's web interface on."""

import logging
import sys
from pathlib import Path

from reflektortts.apps.detector import RunningApp
from reflektortts.apps.executable import ExecutableError, executable_path
from reflektortts.pipeline.plugins import SourcePlugin, load_schema
from reflektortts.profiles.model import SourceSettings
from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.integration import VlcIntegration
from reflektortts.sources.vlc.source import VlcSource
from reflektortts.sources.vlc.vlcrc import vlcrc_path
from reflektortts.sources.vlc.web_settings import SettingsFile

logger = logging.getLogger(__name__)


def portable_folder(pid: int) -> Path | None:
    """The folder a portable VLC on Windows keeps its settings in (portable next to vlc.exe),
    or None for an installed VLC."""
    if sys.platform != "win32":
        return None
    try:
        folder = executable_path(pid).parent / "portable"
    except ExecutableError as error:
        logger.warning("Cannot tell whether VLC is a portable copy: %s", error)
        return None
    return folder if folder.is_dir() else None


def create(source: SourceSettings, app: RunningApp) -> VlcSource:
    if portable_folder(app.process.pid) is not None:
        raise VlcError("This VLC is a portable copy: ReflektorTTS sets up only the installed VLC.")
    return VlcSource(source.name, source.poll_interval, SettingsFile(vlcrc_path()))


def create_integration(state_file: Path) -> VlcIntegration:
    return VlcIntegration(state_file, vlcrc_path())


PLUGIN = SourcePlugin(
    type="vlc",
    settings_schema=load_schema("reflektortts.sources.vlc", "settings.schema.json"),
    create=create,
    integration=create_integration,
)
