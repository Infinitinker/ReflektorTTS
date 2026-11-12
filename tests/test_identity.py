"""Which ReflektorTTS this is: a release is always the installed one, a run from source Dev or E2E."""

import sys

import pytest

from reflektortts.identity import MODE_VARIABLE, RunModeError, app_name


@pytest.mark.parametrize(
    ("mode", "name"), [(None, "ReflektorTTS Dev"), ("dev", "ReflektorTTS Dev"), ("e2e", "ReflektorTTS E2E")]
)
def test_a_run_from_source_has_a_name_of_its_own(monkeypatch: pytest.MonkeyPatch, mode: str | None, name: str) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    if mode is None:
        monkeypatch.delenv(MODE_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(MODE_VARIABLE, mode)

    assert app_name() == name


@pytest.mark.parametrize("mode", [None, "dev", "e2e", "anything"])
def test_a_release_is_always_the_installed_reflektortts(monkeypatch: pytest.MonkeyPatch, mode: str | None) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    if mode is None:
        monkeypatch.delenv(MODE_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(MODE_VARIABLE, mode)

    assert app_name() == "ReflektorTTS"


def test_a_mode_that_does_not_exist_says_which_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv(MODE_VARIABLE, "Dev ")

    with pytest.raises(RunModeError, match='"Dev ": set it to dev or e2e'):
        app_name()
