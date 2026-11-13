"""Whether the desktop has a tray to show ReflektorTTS's icon in.

Windows always has one. On Linux, pystray's X11 icon shows only in a tray that owns the X selection
_NET_SYSTEM_TRAY_S<screen> (the XEmbed system tray): KDE, Xfce and GNOME with the AppIndicator
extension have one, plain GNOME does not.
"""

import sys


def tray_available() -> bool:
    if sys.platform == "win32":
        return True
    # python-xlib, through which pystray draws its icon, is installed only on Linux.
    from Xlib import X
    from Xlib.display import Display

    display = Display()
    try:
        tray = display.intern_atom(f"_NET_SYSTEM_TRAY_S{display.get_default_screen()}")
        return bool(display.get_selection_owner(tray) != X.NONE)
    finally:
        display.close()
