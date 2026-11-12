"""The command line options: only the desktop app can start hidden."""

import pytest

from reflektortts.arguments import parse_arguments


def test_the_desktop_app_can_start_hidden() -> None:
    assert parse_arguments("reflektortts-desktop", ["--hidden"], desktop=True).hidden
    assert not parse_arguments("reflektortts-desktop", [], desktop=True).hidden


def test_the_console_command_has_no_hidden_option() -> None:
    with pytest.raises(SystemExit):
        parse_arguments("reflektortts", ["--hidden"])
