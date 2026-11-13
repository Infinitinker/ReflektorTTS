"""Which ReflektorTTS this is: the installed one, a run from source, or the one under the end-to-end
test. Each has a name of its own, which names its per-user folders, the mutexes the installer looks
for and the autostart entry, and a port of its own for the local API, so a run from source never
touches the installed ReflektorTTS's files, is never taken for it and never keeps it from starting.

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
API_PORTS = {INSTALLED: 47821, NAMES["dev"]: 47822, NAMES["e2e"]: 47823}
"""The local API's port for each name. The native clients connect to the installed ReflektorTTS's
unless told another: the core gives the overlay its port, and the desktop app gives the settings
window the same port (native/shared/transport.h)."""


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


def api_port() -> int:
    """The port this ReflektorTTS's local API listens on (API_PORTS).

    Raises RunModeError, as app_name does."""
    return API_PORTS[app_name()]
