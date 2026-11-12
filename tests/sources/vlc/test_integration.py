"""The VLC integration: VLC's web interface turned on for this computer, and exactly what it changed put back."""

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from reflektortts.apps.detector import ProcessInfo
from reflektortts.integrations import IntegrationError, IntegrationState, IntegrationStatus
from reflektortts.sources.vlc.integration import CLOSE_VLC, NOT_OURS, VlcIntegration
from reflektortts.sources.vlc.web_settings import NOT_FOUND
from tests.sources.vlc.fake_vlcrc import FRESH, with_lines

PASSWORD = "generated-password"
ENABLED_FRESH = (
    FRESH.replace(b"#http-password=\n", f"http-password={PASSWORD}\n".encode())
    .replace(b"#http-host=\n", b"http-host=127.0.0.1\n")
    .replace(b"#extraintf=\n", b"extraintf=http\n")
)


class Processes:
    """The processes running, by name."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def __call__(self) -> Iterator[ProcessInfo]:
        return (ProcessInfo(pid, name) for pid, name in enumerate(self.names, start=1))


class Setup:
    def __init__(self, tmp_path: Path, rc: bytes | None) -> None:
        self.vlcrc = tmp_path / "vlc" / "vlcrc"
        self.state_file = tmp_path / "state" / "integrations" / "vlc.json"
        if rc is not None:
            self.vlcrc.parent.mkdir()
            self.vlcrc.write_bytes(rc)
        self.processes = Processes()
        self.integration = VlcIntegration(self.state_file, self.vlcrc, self.processes, lambda: PASSWORD)

    def records(self) -> dict[str, dict[str, str | None]]:
        changes: dict[str, dict[str, str | None]] = json.loads(self.state_file.read_text("utf-8"))["changes"]
        return changes


def setup(tmp_path: Path, rc: bytes | None = FRESH) -> Setup:
    return Setup(tmp_path, rc)


def test_creating_the_integration_touches_no_files(tmp_path: Path) -> None:
    VlcIntegration(tmp_path / "state.json", tmp_path / "vlcrc")

    assert list(tmp_path.iterdir()) == []


def test_enabling_turns_the_web_interface_on_for_this_computer_with_a_new_password(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    assert vlc.integration.state() == IntegrationState(IntegrationStatus.DISABLED)

    vlc.integration.enable()

    assert vlc.vlcrc.read_bytes() == ENABLED_FRESH
    assert vlc.integration.state() == IntegrationState(IntegrationStatus.ENABLED)


def test_the_state_file_records_what_was_changed_but_never_the_password(tmp_path: Path) -> None:
    vlc = setup(tmp_path)

    vlc.integration.enable()

    assert PASSWORD not in vlc.state_file.read_text("utf-8")
    assert vlc.records() == {
        "extraintf": {"original": "#extraintf=", "written": "http"},
        "http-host": {"original": "#http-host=", "written": "127.0.0.1"},
        "http-password": {"original": "#http-password=", "written": hashlib.sha256(PASSWORD.encode()).hexdigest()},
    }


def test_disabling_puts_the_file_back_byte_for_byte_and_forgets_the_changes(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()

    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == FRESH
    assert not vlc.state_file.exists()
    assert vlc.integration.state() == IntegrationState(IntegrationStatus.DISABLED)


def test_the_web_interface_is_added_to_the_users_other_interfaces_and_only_it_is_removed(tmp_path: Path) -> None:
    vlc = setup(tmp_path, with_lines(FRESH, "extraintf=rc"))
    vlc.integration.enable()
    assert b"\nextraintf=rc:http\n" in vlc.vlcrc.read_bytes()

    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == with_lines(FRESH, "extraintf=rc")


def test_a_module_the_user_added_since_stays_when_the_web_interface_is_removed(tmp_path: Path) -> None:
    vlc = setup(tmp_path, with_lines(FRESH, "extraintf=rc"))
    vlc.integration.enable()
    vlc.vlcrc.write_bytes(vlc.vlcrc.read_bytes().replace(b"extraintf=rc:http", b"extraintf=rc:http:telnet"))

    vlc.integration.disable()

    assert b"\nextraintf=rc:telnet\n" in vlc.vlcrc.read_bytes()


@pytest.mark.parametrize(
    "lines",
    [("http-host=0.0.0.0",), ("extraintf=http", "http-host=192.168.1.5"), ("http-host=0.0.0.0", "http-password=old")],
)
def test_a_web_interface_that_did_not_work_is_limited_to_this_computer(tmp_path: Path, lines: tuple[str, ...]) -> None:
    # Left from a remote on a phone, say, set up to listen on the network but not working.
    before = with_lines(FRESH, *lines)
    vlc = setup(tmp_path, before)

    vlc.integration.enable()

    assert vlc.vlcrc.read_bytes().count(b"\nhttp-host=") == 1
    assert b"\nhttp-host=127.0.0.1\n" in vlc.vlcrc.read_bytes()
    assert vlc.integration.state() == IntegrationState(IntegrationStatus.ENABLED)
    vlc.integration.disable()
    assert vlc.vlcrc.read_bytes() == before


def test_a_host_on_this_computer_is_kept(tmp_path: Path) -> None:
    vlc = setup(tmp_path, with_lines(FRESH, "http-host=localhost"))

    vlc.integration.enable()

    assert b"\nhttp-host=localhost\n" in vlc.vlcrc.read_bytes()
    assert "http-host" not in vlc.records()


def test_a_password_the_user_has_is_kept(tmp_path: Path) -> None:
    vlc = setup(tmp_path, with_lines(FRESH, "http-password=mine"))

    vlc.integration.enable()

    assert b"\nhttp-password=mine\n" in vlc.vlcrc.read_bytes()
    assert "http-password" not in vlc.records()
    vlc.integration.disable()
    assert vlc.vlcrc.read_bytes() == with_lines(FRESH, "http-password=mine")


def test_settings_the_user_changed_since_are_left_alone(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()
    changed = (
        vlc.vlcrc.read_bytes()
        .replace(b"http-host=127.0.0.1", b"http-host=192.168.1.2")
        .replace(PASSWORD.encode(), b"chosen")
    )
    vlc.vlcrc.write_bytes(changed)

    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == (
        FRESH.replace(b"#http-host=\n", b"http-host=192.168.1.2\n").replace(
            b"#http-password=\n", b"http-password=chosen\n"
        )
    )


def test_a_web_interface_the_user_set_up_counts_as_enabled_and_is_left_alone(tmp_path: Path) -> None:
    own = with_lines(FRESH, "extraintf=http", "http-password=remote")
    vlc = setup(tmp_path, own)
    assert vlc.integration.state() == IntegrationState(IntegrationStatus.ENABLED)

    vlc.integration.enable()

    assert vlc.vlcrc.read_bytes() == own
    assert not vlc.state_file.exists()
    with pytest.raises(IntegrationError, match=re.escape(NOT_OURS)):
        vlc.integration.disable()


def test_disabling_what_was_never_enabled_changes_nothing(tmp_path: Path) -> None:
    vlc = setup(tmp_path)

    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == FRESH


def test_enabling_again_after_the_user_turned_the_interface_off_keeps_the_first_records(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()
    vlc.vlcrc.write_bytes(vlc.vlcrc.read_bytes().replace(b"extraintf=http", b"extraintf="))

    vlc.integration.enable()
    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == FRESH.replace(b"#extraintf=\n", b"extraintf=\n")


@pytest.mark.parametrize("name", ["vlc.exe", "VLC.EXE", "vlc"])
def test_vlc_must_be_closed_first(tmp_path: Path, name: str) -> None:
    vlc = setup(tmp_path)
    vlc.processes.names = ["explorer.exe", name]

    with pytest.raises(IntegrationError, match=CLOSE_VLC):
        vlc.integration.enable()
    vlc.processes.names = []
    vlc.integration.enable()
    vlc.processes.names = [name]
    with pytest.raises(IntegrationError, match=CLOSE_VLC):
        vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == ENABLED_FRESH


def test_without_vlcs_settings_file_the_integration_is_unavailable(tmp_path: Path) -> None:
    vlc = setup(tmp_path, None)

    assert vlc.integration.state() == IntegrationState(IntegrationStatus.UNAVAILABLE, NOT_FOUND)
    with pytest.raises(IntegrationError, match=NOT_FOUND):
        vlc.integration.enable()
    assert not vlc.vlcrc.exists()


def test_a_settings_file_that_cannot_be_read_makes_it_unavailable(tmp_path: Path) -> None:
    vlc = setup(tmp_path, None)
    vlc.vlcrc.mkdir(parents=True)

    state = vlc.integration.state()

    assert state.status is IntegrationStatus.UNAVAILABLE
    assert state.reason is not None and state.reason.startswith("Cannot read VLC's settings file")


def test_records_of_a_settings_file_that_is_gone_are_dropped(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()
    vlc.vlcrc.unlink()

    vlc.integration.disable()

    assert not vlc.state_file.exists()


def test_a_read_only_settings_file_is_refused_and_nothing_is_recorded(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    os.chmod(vlc.vlcrc, stat.S_IREAD)
    try:
        with pytest.raises(IntegrationError, match="VLC's settings file is read-only"):
            vlc.integration.enable()
    finally:
        os.chmod(vlc.vlcrc, stat.S_IREAD | stat.S_IWRITE)

    assert vlc.vlcrc.read_bytes() == FRESH
    assert not vlc.state_file.exists()


def test_a_linked_settings_file_is_changed_where_it_points(tmp_path: Path) -> None:
    target = tmp_path / "dotfiles" / "vlcrc"
    target.parent.mkdir()
    target.write_bytes(FRESH)
    vlc = setup(tmp_path, None)
    vlc.vlcrc.parent.mkdir()
    try:
        vlc.vlcrc.symlink_to(target)
    except OSError:
        pytest.skip("Creating links needs a privilege here")

    vlc.integration.enable()

    assert vlc.vlcrc.is_symlink()
    assert target.read_bytes() == ENABLED_FRESH


@pytest.mark.parametrize("content", ["{not json", '{"changes": ["a"]}', '{"changes": {"extraintf": "str"}}', "[]"])
def test_disabling_with_a_damaged_record_says_how_to_turn_the_interface_off_in_vlc(
    tmp_path: Path, content: str
) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()
    vlc.state_file.write_text(content, "utf-8")
    enabled = vlc.vlcrc.read_bytes()

    with pytest.raises(IntegrationError) as raised:
        vlc.integration.disable()

    message = str(raised.value)
    assert message.startswith("The record of what Enable changed in VLC's settings is damaged (")
    assert str(vlc.state_file) in message
    assert message.endswith("Interface > Main interfaces: clear Web).")
    assert vlc.vlcrc.read_bytes() == enabled
    assert vlc.state_file.read_text("utf-8") == content


def test_a_broken_record_among_usable_ones_is_ignored(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.integration.enable()
    records = vlc.records() | {"other": {"written": "x"}}
    vlc.state_file.write_text(json.dumps({"changes": records}), "utf-8")

    vlc.integration.disable()

    assert vlc.vlcrc.read_bytes() == FRESH
    assert not vlc.state_file.exists()


def test_a_damaged_record_of_an_interface_that_is_off_is_dropped(tmp_path: Path) -> None:
    vlc = setup(tmp_path)
    vlc.state_file.parent.mkdir(parents=True)
    vlc.state_file.write_text('{"changes": {"http-host": {"written": 5}, "other": {"written": "x"}}}', "utf-8")

    vlc.integration.disable()
    assert vlc.vlcrc.read_bytes() == FRESH

    vlc.integration.enable()
    vlc.integration.disable()
    assert vlc.vlcrc.read_bytes() == FRESH
