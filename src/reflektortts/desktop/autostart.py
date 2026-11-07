"""Starting ReflektorTTS, hidden in the tray, when the user signs in to Windows: an entry under the
user's Run key, the one Task Manager lists under Startup apps and can disable too. Only
ReflektorTTS.exe from a release can be started that way; run from source, or elsewhere than on
Windows, it is not available."""

import logging
import sys
from pathlib import Path
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
"""Where Task Manager keeps an entry it disabled, under the same name."""
NAME = "ReflektorTTS"
"""The entry's name; tools/installer.iss writes and removes the same one."""
HIDDEN = "--hidden"

logger = logging.getLogger(__name__)


class UserRegistry(Protocol):
    """Values in the current user's registry (HKEY_CURRENT_USER)."""

    def read(self, key: str, name: str) -> object | None: ...
    def write(self, key: str, name: str, text: str) -> None: ...
    def delete(self, key: str, name: str) -> None:
        """Does nothing if the value does not exist."""
        ...


class Autostart:
    def __init__(self, registry: UserRegistry, executable: Path) -> None:
        self._registry = registry
        self._command = f'"{executable}" {HIDDEN}'

    def enabled(self) -> bool:
        """Whether Windows starts this ReflektorTTS.exe at sign-in: the entry runs it, and Task
        Manager has not disabled the entry."""
        command = self._registry.read(RUN_KEY, NAME)
        if not isinstance(command, str) or command.casefold() != self._command.casefold():
            return False
        approved = self._registry.read(APPROVED_KEY, NAME)
        # Task Manager marks a disabled entry with an odd first byte (3), an enabled one with an even one.
        return not (isinstance(approved, bytes) and approved[:1] and approved[0] % 2 == 1)

    def enable(self, enabled: bool) -> None:
        """Raises OSError if the registry cannot be changed."""
        if enabled:
            self._registry.write(RUN_KEY, NAME, self._command)
        else:
            self._registry.delete(RUN_KEY, NAME)
        # Last, so a failure above leaves things as they were: Task Manager's mark would keep a new
        # entry disabled, and without the entry it means nothing.
        self._registry.delete(APPROVED_KEY, NAME)


if sys.platform == "win32":
    import winreg

    class WindowsRegistry:
        """The current user's registry, through winreg."""

        def read(self, key: str, name: str) -> object | None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                    value: object = winreg.QueryValueEx(handle, name)[0]
            except FileNotFoundError:
                return None
            except OSError as error:
                # E.g. a policy that hides the key: ReflektorTTS then counts as not starting with Windows.
                logger.warning("Cannot read %s in the registry: %s", key, error)
                return None
            return value

        def write(self, key: str, name: str, text: str) -> None:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, access=winreg.KEY_SET_VALUE) as handle:
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, text)

        def delete(self, key: str, name: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, access=winreg.KEY_SET_VALUE) as handle:
                    winreg.DeleteValue(handle, name)
            except FileNotFoundError:
                pass  # Nothing to delete.


def system_autostart() -> Autostart | None:
    """This ReflektorTTS.exe's autostart, or None where it is not available."""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return Autostart(WindowsRegistry(), Path(sys.executable))
    return None
