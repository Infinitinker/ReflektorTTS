"""The programs of the end-to-end test: the desktop app run from source, and the fake VLC under
VLC's name; starting them, and stopping each with every process it started."""

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import venv
from pathlib import Path

import psutil

from reflektortts.api.server import HOST
from reflektortts.identity import MODE_VARIABLE
from tests.e2e import fake_vlc
from tests.e2e.folders import FAKE_VLC, ROOT, user_folders


def port_taken(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex((HOST, port)) == 0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def vlc_running() -> bool:
    return any((process.info["name"] or "").lower() in ("vlc.exe", "vlc") for process in psutil.process_iter(["name"]))


def environment() -> dict[str, str]:
    """This process's environment with the per-user folders of the run, which ReflektorTTS runs in
    as ReflektorTTS E2E."""
    return {**os.environ, **user_folders(), MODE_VARIABLE: "e2e"}


def start_reflektortts(log: Path) -> subprocess.Popen[bytes]:
    """Starts the desktop app with this Python, its console output going to log."""
    with log.open("wb") as output:
        return subprocess.Popen(
            [sys.executable, "-m", "reflektortts.desktop"],
            cwd=ROOT,
            env=environment(),
            stdout=output,
            stderr=subprocess.STDOUT,
        )


def vlc_program() -> Path:
    """A Python that runs as vlc.exe or vlc: on Windows the launcher of a new virtual environment
    copied under that name, which starts its environment's Python; on Linux a link to the Python
    this one is built on, whose name the process takes."""
    base = Path(getattr(sys, "_base_executable", sys.executable))
    if sys.platform == "win32":
        venv.create(FAKE_VLC, with_pip=False)
        program = FAKE_VLC / "Scripts" / "vlc.exe"
        shutil.copy2(FAKE_VLC / "Scripts" / "python.exe", program)
        return program
    FAKE_VLC.mkdir(parents=True)
    program = FAKE_VLC / "vlc"
    program.symlink_to(base.resolve())
    return program


def start_fake_vlc(port: int, password: str, media: Path, log: Path) -> subprocess.Popen[bytes]:
    with log.open("wb") as output:
        return subprocess.Popen(
            [str(vlc_program()), "-I", fake_vlc.__file__, str(port), password, str(media)],
            stdout=output,
            stderr=subprocess.STDOUT,
        )


def stop(process: subprocess.Popen[bytes]) -> None:
    """Kills the process and every process it started (the TTS process, the Python a launcher starts)."""
    try:
        parent = psutil.Process(process.pid)
        family = [parent, *parent.children(recursive=True)]
    except psutil.NoSuchProcess:
        family = []
    for member in family:
        with contextlib.suppress(psutil.NoSuchProcess):
            member.kill()
    psutil.wait_procs(family, timeout=30)
    process.wait(timeout=30)
