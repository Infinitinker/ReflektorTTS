"""Starting ReflektorTTS when the user signs in: its entry under the Run key, and Task Manager's mark."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from reflektortts.desktop.system.autostart import APPROVED_KEY, NAME, RUN_KEY, Autostart

EXE = Path(r"C:\Users\me\AppData\Local\Programs\ReflektorTTS\reflektortts.exe")
COMMAND = f'"{EXE}" --hidden'
DISABLED_BY_TASK_MANAGER = bytes([3]) + bytes(11)
ENABLED_BY_TASK_MANAGER = bytes([2]) + bytes(11)


class FakeRegistry:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], object] = {}

    def read(self, key: str, name: str) -> object | None:
        return self.values.get((key, name))

    def write(self, key: str, name: str, text: str) -> None:
        self.values[(key, name)] = text

    def delete(self, key: str, name: str) -> None:
        self.values.pop((key, name), None)


def test_enabling_adds_a_hidden_start_of_this_exe_and_disabling_removes_it() -> None:
    registry = FakeRegistry()
    autostart = Autostart(registry, EXE)
    assert not autostart.enabled()

    autostart.enable(True)

    assert registry.values == {(RUN_KEY, NAME): COMMAND}
    assert autostart.enabled()

    autostart.enable(False)

    assert registry.values == {}
    assert not autostart.enabled()


def test_an_entry_for_another_copy_does_not_count() -> None:
    registry = FakeRegistry()
    registry.write(RUN_KEY, NAME, r'"D:\Old\ReflektorTTS\reflektortts.exe" --hidden')

    assert not Autostart(registry, EXE).enabled()


def test_the_path_is_compared_without_case() -> None:
    registry = FakeRegistry()
    registry.write(RUN_KEY, NAME, COMMAND.upper().replace("--HIDDEN", "--hidden"))

    assert Autostart(registry, EXE).enabled()


def test_an_entry_disabled_in_task_manager_is_off_until_enabled_again() -> None:
    registry = FakeRegistry()
    registry.write(RUN_KEY, NAME, COMMAND)
    registry.values[(APPROVED_KEY, NAME)] = DISABLED_BY_TASK_MANAGER
    autostart = Autostart(registry, EXE)
    assert not autostart.enabled()

    autostart.enable(True)

    assert autostart.enabled()
    assert (APPROVED_KEY, NAME) not in registry.values


def test_an_entry_enabled_in_task_manager_counts() -> None:
    registry = FakeRegistry()
    registry.write(RUN_KEY, NAME, COMMAND)
    registry.values[(APPROVED_KEY, NAME)] = ENABLED_BY_TASK_MANAGER

    assert Autostart(registry, EXE).enabled()


class FailingRegistry(FakeRegistry):
    def write(self, key: str, name: str, text: str) -> None:
        raise PermissionError("Access is denied")


def test_a_failed_change_leaves_task_managers_mark_alone() -> None:
    registry = FailingRegistry()
    registry.values[(APPROVED_KEY, NAME)] = DISABLED_BY_TASK_MANAGER

    with pytest.raises(OSError):
        Autostart(registry, EXE).enable(True)

    assert registry.values == {(APPROVED_KEY, NAME): DISABLED_BY_TASK_MANAGER}


# The registry exists only on Windows.
if sys.platform == "win32":
    import winreg

    from reflektortts.desktop.system.autostart import WindowsRegistry

    def test_the_windows_registry_reads_writes_and_deletes_values() -> None:
        key = rf"Software\ReflektorTTS-test-{uuid4()}"
        registry = WindowsRegistry()
        try:
            assert registry.read(key, NAME) is None
            registry.delete(key, NAME)  # A missing key or value is no error.

            registry.write(key, NAME, COMMAND)
            assert registry.read(key, NAME) == COMMAND

            registry.delete(key, NAME)
            assert registry.read(key, NAME) is None
        finally:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
