"""A label that always takes the same number of lines: a longer text is cut with an ellipsis and
shown whole while the mouse is over it, so the widgets below never move."""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from reflektortts.desktop.text_fit import fit_lines

TOOLTIP_PADDING = ("4.5p", "3p")
"""Around the whole text, in points, so it scales with the display like the text."""


class ClampedLabel:
    def __init__(self, parent: tk.Misc, lines: int) -> None:
        """Grid or pack frame; it is as wide as its place and lines of the label's font tall."""
        self._font = tkfont.Font(font=ttk.Style().lookup("TLabel", "font") or "TkDefaultFont")
        self._lines = lines
        self.frame = ttk.Frame(parent)
        self.frame.grid_propagate(False)
        self.frame.pack_propagate(False)
        self._label = ttk.Label(self.frame, text="", justify="left", anchor="nw")
        self._label.pack(fill="both", expand=True)
        # As tall as the label asks to be for that many lines, its own padding included.
        self._label.configure(text="\n".join(["Ag"] * lines))
        self.frame.configure(height=self._label.winfo_reqheight())
        self._text = ""
        self._cut = False
        self._tooltip: tk.Toplevel | None = None
        self.frame.bind("<Configure>", lambda event: self._fit())
        self._label.bind("<Enter>", lambda event: self._show_whole())
        self._label.bind("<Leave>", lambda event: self._hide_whole())
        # Hiding the window, or switching to another tab, comes without a <Leave>. The window is in
        # every widget's bindtags, so it hears the tab's frame being unmapped too.
        self.frame.winfo_toplevel().bind("<Unmap>", lambda event: self._hide_whole(), add="+")

    def configure(self, text: str, foreground: str) -> None:
        if text != self._text:
            self._hide_whole()
        self._text = text
        self._label.configure(foreground=foreground)
        self._fit()

    def _fit(self) -> None:
        width = self.frame.winfo_width()
        if width <= 1:  # Not laid out yet; <Configure> fits it once it is.
            self._cut = False
            self._label.configure(text=self._text)
            return
        fitted = fit_lines(self._text, width, self._font.measure, self._lines)
        self._cut = fitted.cut
        self._label.configure(text="\n".join(fitted.lines))
        if not fitted.cut:
            self._hide_whole()

    def _show_whole(self) -> None:
        """Shows the whole text under the label, as wide as it, kept on the screen."""
        if not self._cut or self._tooltip is not None:
            return
        tooltip = tk.Toplevel(self.frame)
        tooltip.wm_overrideredirect(True)
        ttk.Label(
            tooltip,
            text=self._text,
            justify="left",
            wraplength=self.frame.winfo_width(),
            padding=TOOLTIP_PADDING,
            relief="solid",
            borderwidth=1,
        ).pack()
        tooltip.update_idletasks()
        screen_right = self.frame.winfo_vrootx() + self.frame.winfo_vrootwidth()
        screen_bottom = self.frame.winfo_vrooty() + self.frame.winfo_vrootheight()
        x = min(self.frame.winfo_rootx(), screen_right - tooltip.winfo_reqwidth())
        y = self.frame.winfo_rooty() + self.frame.winfo_height()
        if y + tooltip.winfo_reqheight() > screen_bottom:
            y = self.frame.winfo_rooty() - tooltip.winfo_reqheight()
        tooltip.wm_geometry(f"+{max(x, self.frame.winfo_vrootx())}+{y}")
        tooltip.lift()
        self._tooltip = tooltip

    def _hide_whole(self) -> None:
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
