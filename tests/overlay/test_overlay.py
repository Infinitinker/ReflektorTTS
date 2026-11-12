"""Where the overlay has no implementation for the system, the app is read without it."""

import pytest

from reflektortts.overlay import inject_overlay


def test_other_systems_read_the_app_without_the_overlay(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("sys.platform", "linux")

    assert inject_overlay(42, []) is False
    assert "not available on this system yet" in caplog.text
