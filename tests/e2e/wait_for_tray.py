"""Waits for a tray on the X screen, for the Linux E2E tests job: python -m tests.e2e.wait_for_tray.

The app looks for a tray once, as it starts, so the tray started just before it must be up first.
"""

import sys
import time

from reflektortts.desktop.system.tray_host import tray_available

SECONDS = 15


def main() -> None:
    deadline = time.monotonic() + SECONDS
    while not tray_available():
        if time.monotonic() > deadline:
            sys.exit(f"No tray appeared within {SECONDS} seconds.")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
