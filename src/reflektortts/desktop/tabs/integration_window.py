"""The window the Profiles tab's Integration… button opens: for the selected profile, one group per
integration its sources need, titled with the integration's name, with what it does, its state and a
button that enables or disables it. It is modal, so the profile it is about stays the selected one,
and it follows the integrations' state while it is open."""

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from reflektortts.desktop.api.integrations import ACTION_LABELS, IntegrationItem, action, state_text
from reflektortts.desktop.widgets.clamped_label import ClampedLabel
from reflektortts.desktop.widgets.tables import button_width
from reflektortts.desktop.widgets.theme import BUSY, GOOD

STATE_COLORS = {"enabled": GOOD, "unavailable": BUSY}
"""Text color of the state: green when enabled, amber when it cannot be; otherwise the default."""
STATE_LINES = 2
"""The state always takes this many lines, so a long reason never moves what is below it."""
TEXT_WIDTH = 440
"""Pixels the texts wrap at, which sets the window's width."""
PADDING = 12


class IntegrationWindow:
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        items: Sequence[IntegrationItem],
        on_change: Callable[[IntegrationItem, bool], None],
        on_close: Callable[[], None],
    ) -> None:
        """on_change is given an integration and whether to enable it; on_close is called once the
        window is closed."""
        self._on_close = on_close
        self._owner = parent.winfo_toplevel()
        self.window = tk.Toplevel(parent)
        self.window.withdraw()  # Shown once centered, so it does not jump.
        self.window.title(title)
        self.window.resizable(False, False)
        self.window.transient(self._owner)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        content = ttk.Frame(self.window, padding=PADDING)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, minsize=TEXT_WIDTH)
        self._groups = [_Group(content, row, item, on_change) for row, item in enumerate(items)]
        # Tk hides a transient window with its owner but never shows it again, while it keeps the
        # grab: so it closes when the owner is hidden or minimized. Unmaps of the owner's widgets
        # (another tab) reach this binding too, and are ignored.
        self._unmap_binding = self._owner.bind(
            "<Unmap>", lambda event: self.close() if event.widget is self._owner else None, add="+"
        )
        self.window.update_idletasks()
        self._center_on(self._owner)
        self.window.deiconify()
        self.window.wait_visibility()  # A grab fails on a window not shown yet (X11).
        self.window.grab_set()
        if self._groups:
            self._groups[0].focus()

    @property
    def ids(self) -> list[str]:
        """The integrations shown, in order."""
        return [group.item.id for group in self._groups]

    def show(self, items: Sequence[IntegrationItem]) -> None:
        """Shows the integrations' new state; items are the same integrations as at the start."""
        for group, item in zip(self._groups, items, strict=True):
            group.show(item)

    def close(self) -> None:
        self._owner.unbind("<Unmap>", self._unmap_binding)
        self.window.grab_release()
        self.window.destroy()
        self._on_close()

    def _center_on(self, owner: tk.Misc) -> None:
        x = owner.winfo_rootx() + (owner.winfo_width() - self.window.winfo_reqwidth()) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - self.window.winfo_reqheight()) // 3
        self.window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class _Group:
    def __init__(
        self,
        parent: ttk.Frame,
        row: int,
        item: IntegrationItem,
        on_change: Callable[[IntegrationItem, bool], None],
    ) -> None:
        self.item = item
        self._on_change = on_change
        frame = ttk.LabelFrame(parent, text=item.name, padding=(8, 2, 8, 6))
        frame.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 8, 0))
        frame.columnconfigure(1, weight=1)
        self._description = ttk.Label(frame, text="", justify="left", wraplength=TEXT_WIDTH)
        self._description.grid(row=0, column=0, columnspan=2, sticky="w")
        self._button = ttk.Button(frame, text=ACTION_LABELS[0], width=button_width(ACTION_LABELS), command=self._act)
        self._button.grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self._state = ClampedLabel(frame, STATE_LINES)
        self._state.frame.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(10, 0))
        self.show(item)

    def show(self, item: IntegrationItem) -> None:
        self.item = item
        self._description.configure(text=item.description)
        self._state.configure(text=state_text(item), foreground=STATE_COLORS.get(item.state, ""))
        label, clickable = action(item)
        self._button.configure(text=label, state="normal" if clickable else "disabled")

    def focus(self) -> None:
        """Gives the button the keyboard focus, so Space clicks it."""
        self._button.focus_set()

    def _act(self) -> None:
        label, clickable = action(self.item)
        if clickable:
            self._on_change(self.item, label == ACTION_LABELS[0])
