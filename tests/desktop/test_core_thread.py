import threading
from collections.abc import Sequence
from pathlib import Path

from reflektortts.core import NoProfilesError
from reflektortts.desktop.core_thread import CoreThread


def test_the_core_runs_until_stopped(tmp_path: Path) -> None:
    started = threading.Event()
    seen: list[tuple[Path, Path, tuple[Path, ...]]] = []

    def run_core(profiles: Path, settings: Path, overlay: Sequence[Path], stop: threading.Event) -> None:
        seen.append((profiles, settings, tuple(overlay)))
        started.set()
        stop.wait()

    core = CoreThread(tmp_path / "profiles", tmp_path / "settings", [tmp_path / "overlay"], run_core)
    core.start()
    assert started.wait(5)
    assert not core.stopped()

    core.stop()

    assert core.stopped() and core.error is None
    assert seen == [(tmp_path / "profiles", tmp_path / "settings", (tmp_path / "overlay",))]


def test_why_the_core_stopped_on_its_own_is_kept(tmp_path: Path) -> None:
    def run_core(profiles: Path, settings: Path, overlay: Sequence[Path], stop: threading.Event) -> None:
        raise NoProfilesError("No app profiles in profiles.")

    core = CoreThread(tmp_path, tmp_path, [], run_core)
    core.start()
    core.stop()

    assert isinstance(core.error, NoProfilesError)
