"""Which ReflektorTTS this is: the installed one, a run from source, or the one under the end-to-end
test. Each has a name of its own, which names its per-user folders, the mutexes the installer looks
for and the autostart entry, so a run from source never touches the installed ReflektorTTS's files
and is never taken for it.

A release (a frozen reflektortts.exe) is always the installed ReflektorTTS, whatever its environment
says. A run from source is "ReflektorTTS Dev", unless the REFLEKTORTTS_MODE environment variable
says "e2e", as the end-to-end test sets it; start.bat sets "dev".
"""

import os
import sys

INSTALLED = "ReflektorTTS"
MODE_VARIABLE = "REFLEKTORTTS_MODE"
NAMES = {"dev": "ReflektorTTS Dev", "e2e": "ReflektorTTS E2E"}
"""The name of a run from source in each mode."""


class RunModeError(ValueError):
    """REFLEKTORTTS_MODE names no mode."""


def app_name() -> str:
    """The name this ReflektorTTS goes by: "ReflektorTTS", "ReflektorTTS Dev" or "ReflektorTTS E2E".

    Raises RunModeError if a run from source is given a mode that does not exist."""
    if getattr(sys, "frozen", False):
        return INSTALLED
    mode = os.environ.get(MODE_VARIABLE) or "dev"
    if mode not in NAMES:
        raise RunModeError(f'{MODE_VARIABLE} is "{mode}": set it to {" or ".join(NAMES)}, or leave it unset for dev.')
    return NAMES[mode]
