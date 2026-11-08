import os
from pathlib import Path

import pytest

from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.vlcrc import Vlcrc
from reflektortts.sources.vlc.web_settings import NOT_FOUND, SettingsFile, WebSettings, web_settings
from tests.sources.vlc.fake_vlcrc import FRESH, with_lines

READY = with_lines(FRESH, "extraintf=http", "http-password=secret", "http-host=127.0.0.1")


def test_a_fresh_vlcrc_has_the_web_interface_off_on_port_8080() -> None:
    assert web_settings(Vlcrc(FRESH)) == WebSettings(interface_on=False, password=b"", host="", port=8080)


@pytest.mark.parametrize("line", ["extraintf=rc:http", "extraintf=luahttp", "control=HTTP", "intf=http"])
def test_the_web_interface_is_on_when_any_interface_list_names_it(line: str) -> None:
    assert web_settings(Vlcrc(with_lines(FRESH, line))).interface_on


def test_without_a_password_the_web_interface_is_not_ready() -> None:
    assert not web_settings(Vlcrc(with_lines(FRESH, "extraintf=http"))).ready
    assert web_settings(Vlcrc(READY)).ready


@pytest.mark.parametrize(("value", "port"), [("9090", 9090), ("0x2382", 9090), ("70000", 8080), ("x", 8080)])
def test_the_port_is_read_as_vlc_reads_it(value: str, port: int) -> None:
    assert web_settings(Vlcrc(with_lines(FRESH, f"http-port={value}"))).port == port


def test_the_settings_are_read_again_when_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "vlcrc"
    path.write_bytes(FRESH)
    settings = SettingsFile(path)
    assert not settings.current().ready

    path.write_bytes(READY)
    os.utime(path, ns=(1, 1))

    assert settings.current().password == b"secret"


def test_the_last_settings_stand_while_vlc_replaces_the_file(tmp_path: Path) -> None:
    path = tmp_path / "vlcrc"
    path.write_bytes(READY)
    settings = SettingsFile(path)
    settings.current()

    path.unlink()

    assert settings.current().password == b"secret"


def test_a_missing_file_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(VlcError) as raised:
        SettingsFile(tmp_path / "vlcrc").current()

    assert str(raised.value) == NOT_FOUND
