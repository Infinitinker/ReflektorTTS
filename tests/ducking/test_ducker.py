import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from reflektortts.apps.detector import ProcessInfo
from reflektortts.ducking.ducker import Ducker, Timing
from reflektortts.ducking.records import DuckRecords

GTA2 = ProcessInfo(pid=42, name="gta2.exe")
INSTANT = Timing(fade_down=0.0, hold=0.0, fade_up=0.0, step=0.0)
TIMEOUT = 2.0


class FakeVolume:
    def __init__(self, level: float) -> None:
        self.level = level
        self.fail = False

    def get(self) -> float:
        return self.level

    def set(self, level: float) -> None:
        if self.fail:
            raise OSError("the session has expired")
        self.level = level


class FakeMixer:
    """Finds the volume of pid 42 once the app plays sound."""

    def __init__(self, volume: FakeVolume | None) -> None:
        self.volume = volume
        self.lookups = 0

    def open(self, pid: int) -> FakeVolume | None:
        self.lookups += 1
        return self.volume if pid == GTA2.pid else None


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def settle() -> None:
    """Gives the ducker's thread time to act, for checks that something did not happen."""
    time.sleep(0.05)


@pytest.fixture
def records(tmp_path: Path) -> DuckRecords:
    return DuckRecords(tmp_path / "lowered-apps.json")


@pytest.fixture
def make_ducker(records: DuckRecords) -> Iterator[Callable[..., Ducker]]:
    duckers: list[Ducker] = []

    def make(mixer: FakeMixer, timing: Timing = INSTANT, enabled: bool = True) -> Ducker:
        duckers.append(Ducker(mixer.open, records, enabled, 0.3, timing))
        return duckers[-1]

    yield make
    for ducker in duckers:
        ducker.close()


def test_the_game_is_lowered_while_speaking_and_restored_after(
    make_ducker: Callable[..., Ducker], records: DuckRecords
) -> None:
    volume = FakeVolume(0.8)
    ducker = make_ducker(FakeMixer(volume))
    ducker.watch(GTA2)

    ducker.speaking(True)
    wait_until(lambda: volume.level == pytest.approx(0.24))
    assert records.get("gta2.exe") == 0.8
    ducker.speaking(False)
    wait_until(lambda: volume.level == 0.8)
    wait_until(lambda: records.get("gta2.exe") is None)


def test_the_game_stays_lowered_between_close_lines_and_close_restores_it(make_ducker: Callable[..., Ducker]) -> None:
    volume = FakeVolume(1.0)
    ducker = make_ducker(FakeMixer(volume), Timing(fade_down=0.0, hold=60.0, fade_up=0.0, step=0.0))
    ducker.watch(GTA2)

    ducker.speaking(True)
    wait_until(lambda: volume.level == pytest.approx(0.3))
    ducker.speaking(False)
    settle()
    assert volume.level == pytest.approx(0.3)
    ducker.close()
    assert volume.level == 1.0


def test_nothing_is_lowered_when_switched_off_and_a_new_level_applies_at_once(
    make_ducker: Callable[..., Ducker],
) -> None:
    volume = FakeVolume(1.0)
    ducker = make_ducker(FakeMixer(volume), enabled=False)
    ducker.watch(GTA2)

    ducker.speaking(True)
    settle()
    assert volume.level == 1.0
    ducker.configure(True, 0.3)
    wait_until(lambda: volume.level == pytest.approx(0.3))
    ducker.configure(True, 0.5)
    wait_until(lambda: volume.level == pytest.approx(0.5))


def test_a_game_left_lowered_by_an_earlier_run_is_restored(
    make_ducker: Callable[..., Ducker], records: DuckRecords
) -> None:
    records.put("gta2.exe", 0.9)
    volume = FakeVolume(0.27)
    ducker = make_ducker(FakeMixer(volume))

    ducker.watch(GTA2)

    wait_until(lambda: volume.level == 0.9)
    # The ducker's thread restores the volume, then removes the record.
    wait_until(lambda: records.get("gta2.exe") is None)


def test_a_leftover_record_is_used_when_the_game_has_no_sound_yet(
    make_ducker: Callable[..., Ducker], records: DuckRecords
) -> None:
    records.put("gta2.exe", 0.9)
    mixer = FakeMixer(None)
    ducker = make_ducker(mixer)
    ducker.watch(GTA2)
    wait_until(lambda: mixer.lookups == 1)

    volume = mixer.volume = FakeVolume(0.27)
    ducker.speaking(True)
    wait_until(lambda: mixer.lookups == 2)
    ducker.speaking(False)
    wait_until(lambda: volume.level == 0.9)


def test_a_game_without_sound_is_looked_up_once_per_stretch_of_speech(make_ducker: Callable[..., Ducker]) -> None:
    mixer = FakeMixer(None)
    ducker = make_ducker(mixer)
    ducker.watch(GTA2)

    ducker.speaking(True)
    settle()

    assert mixer.lookups == 1


def test_a_game_exiting_while_lowered_keeps_its_record(
    make_ducker: Callable[..., Ducker], records: DuckRecords, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    volume = FakeVolume(0.8)
    ducker = make_ducker(FakeMixer(volume), Timing(fade_down=0.0, hold=60.0, fade_up=0.0, step=0.0))
    ducker.watch(GTA2)
    ducker.speaking(True)
    wait_until(lambda: volume.level == pytest.approx(0.24))

    ducker.watch(None)
    wait_until(lambda: "exited while lowered" in caplog.text)
    ducker.close()

    assert volume.level == pytest.approx(0.24)
    assert records.get("gta2.exe") == 0.8


def test_a_failing_volume_is_logged_and_does_not_stop_the_ducker(
    make_ducker: Callable[..., Ducker], caplog: pytest.LogCaptureFixture
) -> None:
    volume = FakeVolume(0.8)
    volume.fail = True
    ducker = make_ducker(FakeMixer(volume))
    ducker.watch(GTA2)

    ducker.speaking(True)
    wait_until(lambda: "Could not change the app's volume" in caplog.text)
    volume.fail = False
    ducker.speaking(False)
    ducker.speaking(True)

    wait_until(lambda: volume.level == pytest.approx(0.24))


def test_an_app_no_longer_read_but_still_running_gets_its_volume_back(
    make_ducker: Callable[..., Ducker], records: DuckRecords
) -> None:
    volume = FakeVolume(0.8)
    ducker = make_ducker(FakeMixer(volume), Timing(fade_down=0.0, hold=60.0, fade_up=0.0, step=0.0))
    ducker.watch(GTA2)
    ducker.speaking(True)
    wait_until(lambda: volume.level == pytest.approx(0.24))

    ducker.watch(None, still_running=True)
    wait_until(lambda: volume.level == pytest.approx(0.8))
    ducker.close()

    assert records.get("gta2.exe") is None
