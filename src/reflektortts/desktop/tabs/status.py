"""The window's Status tab: what ReflektorTTS is doing, with buttons to pause reading and open the
settings of the app being read, and about ReflektorTTS: its version, and links to the project and its
support pages."""

from collections.abc import Callable
from tkinter import ttk

from reflektortts.desktop.about import BUYCOFFEE, KO_FI, LICENSE, About
from reflektortts.desktop.api.status import (
    CoreStatus,
    describe,
    hint,
    languages_text,
    settings_caption,
    sound_text,
)
from reflektortts.desktop.icon import icon_photo
from reflektortts.desktop.widgets.clamped_label import ClampedLabel
from reflektortts.desktop.widgets.status_bar import StatusBar
from reflektortts.desktop.widgets.tables import button_width
from reflektortts.desktop.widgets.theme import BUSY, DIM, GOOD, heading_font, title_font

PADDING = 16
PAUSE_LABELS = ("Pause reading", "Resume reading")
"""The pause button's labels; it is as wide as the longer, so the buttons after it never move."""
HEADER_ICON_SIZE = 48
DETAILS = ("Voice", "Languages", "App sound")
"""The lines under what ReflektorTTS is doing, in its Now box."""
NOW_PADDING = 12
HINT_LINES = 2
"""The line under the status always takes this many lines, so a long message never moves the details."""


def status_color(status: CoreStatus | None) -> str:
    """Green while an app is read, amber while paused or for an unsupported version; empty for the
    default color."""
    if status is None:
        return DIM
    if status.paused or (status.unsupported and not status.app):
        return BUSY
    return GOOD if status.app else ""


def hint_color(status: CoreStatus | None) -> str:
    """Amber when the line under the status says why a source of the app fails, else gray."""
    return BUSY if status is not None and status.app and status.source_error else DIM


def read_app(status: CoreStatus | None, missing: str | None) -> tuple[str, str] | None:
    """The profile and title of the app being read, whose settings App settings… opens; None while
    no app is read, or where there is no settings window (missing says why)."""
    if missing is not None or status is None or status.app is None or status.profile is None:
        return None
    return status.profile, status.app


def app_settings_hint(status: CoreStatus | None, missing: str | None) -> str:
    """What App settings… does, or why it does nothing now."""
    if missing is not None:
        return missing
    app = read_app(status, missing)
    if app is None:
        return "Opens the settings of the app being read. To set up another app, select it in the Profiles tab."
    return f"Change the voice, languages and the rest for {app[1]}, in a window of its own."


class StatusTab:
    def __init__(
        self,
        notebook: ttk.Notebook,
        status_bar: StatusBar,
        on_pause_toggle: Callable[[], None],
        on_read_app_settings: Callable[[str, str], None],
        app_settings_missing: str | None,
        on_quit: Callable[[], None],
        on_open_link: Callable[[str], None],
        about: About,
        language_name: Callable[[str], str],
        voice_title: Callable[[str], str],
    ) -> None:
        self._language_name = language_name
        self._voice_title = voice_title
        self._app_settings_missing = app_settings_missing
        self._shown: CoreStatus | None = None
        """The status shown, which the App settings… hint follows."""
        self._paused = False
        # Kept here: Tkinter drops an image nothing in Python refers to.
        self._header_icon = icon_photo(HEADER_ICON_SIZE)
        self.frame = ttk.Frame(notebook, padding=PADDING)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

        header = ttk.Frame(self.frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, image=self._header_icon).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(header, text="ReflektorTTS", font=title_font()).grid(row=0, column=1, sticky="sw")
        ttk.Label(header, text=f"Your apps, read aloud. Version {about.version}", foreground=DIM).grid(
            row=1, column=1, sticky="nw"
        )
        quit_button = ttk.Button(header, text="Quit", command=on_quit)
        quit_button.grid(row=0, column=2, rowspan=2, sticky="e")
        status_bar.hint(
            quit_button,
            lambda: "Stop reading and close completely. Closing the window keeps it running next to the clock.",
        )

        now = ttk.LabelFrame(self.frame, text="Now", padding=NOW_PADDING)
        now.grid(row=1, column=0, sticky="ew")
        now.columnconfigure(1, weight=1)
        self._status = ttk.Label(now, text=describe(None), font=heading_font(), foreground=status_color(None))
        self._status.grid(row=0, column=0, columnspan=2, sticky="w")
        self._hint = ClampedLabel(now, HINT_LINES)
        self._hint.frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        self._hint.configure(text=hint(None), foreground=DIM)
        self._settings_for = ttk.Label(now, text="", foreground=DIM)
        self._settings_for.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self._details: list[ttk.Label] = []
        for row, name in enumerate(DETAILS, start=3):
            ttk.Label(now, text=name, foreground=DIM).grid(row=row, column=0, sticky="w", padx=(0, 16))
            detail = ttk.Label(now, text="")
            detail.grid(row=row, column=1, sticky="w")
            self._details.append(detail)
        buttons = ttk.Frame(now)
        buttons.grid(row=3 + len(DETAILS), column=0, columnspan=2, sticky="w", pady=(12, 0))
        self._pause = ttk.Button(
            buttons,
            text=PAUSE_LABELS[0],
            width=button_width(PAUSE_LABELS),
            command=on_pause_toggle,
            state="disabled",
        )
        self._pause.grid(row=0, column=0)
        status_bar.hint(self._pause, self._pause_hint)
        self._app_settings = ttk.Button(
            buttons,
            text="App settings…",
            command=lambda: self._open_app_settings(on_read_app_settings),
            state="disabled",
        )
        self._app_settings.grid(row=0, column=1, padx=(6, 0))
        status_bar.hint(self._app_settings, lambda: app_settings_hint(self._shown, self._app_settings_missing))

        links = ttk.Frame(self.frame)
        links.grid(row=3, column=0, sticky="ew")
        links.columnconfigure((0, 1), weight=1, uniform="links")
        project = ttk.LabelFrame(links, text="Project", padding=10)
        project.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        page = ttk.Button(project, text="Project page", command=lambda: on_open_link(about.project))
        page.grid(row=0, column=0)
        report = ttk.Button(project, text="Report a problem", command=lambda: on_open_link(about.issues))
        report.grid(row=0, column=1, padx=(6, 0))
        status_bar.hint(page, lambda: "Open the project's page on GitHub: its code, guides and releases.")
        status_bar.hint(
            report, lambda: "Report a problem on GitHub. The logs help: open their folder in the Settings tab."
        )

        support = ttk.LabelFrame(links, text="Support", padding=10)
        support.grid(row=0, column=1, sticky="nsew")
        ko_fi = ttk.Button(support, text="Ko-fi", command=lambda: on_open_link(KO_FI))
        ko_fi.grid(row=0, column=0)
        buycoffee = ttk.Button(support, text="buycoffee.to", command=lambda: on_open_link(BUYCOFFEE))
        buycoffee.grid(row=0, column=1, padx=(6, 0))
        status_bar.hint(ko_fi, lambda: "Buy the author a coffee on Ko-fi, with a card or PayPal.")
        status_bar.hint(
            buycoffee, lambda: "Buy the author a coffee on buycoffee.to, with BLIK or a Polish bank transfer."
        )

        ttk.Label(self.frame, text=LICENSE, foreground=DIM).grid(row=4, column=0, sticky="w", pady=(10, 0))

    def show(self, status: CoreStatus | None) -> None:
        self._shown = status
        self._paused = status is not None and status.paused
        self._status.configure(text=describe(status), foreground=status_color(status))
        self._hint.configure(text=hint(status), foreground=hint_color(status))
        texts = (
            ("", "", "")
            if status is None
            else (self._voice_title(status.voice), languages_text(status, self._language_name), sound_text(status))
        )
        for label, text in zip(self._details, texts, strict=True):
            label.configure(text=text)
        self._settings_for.configure(text=settings_caption(status))
        self._pause.configure(
            text=PAUSE_LABELS[1] if self._paused else PAUSE_LABELS[0],
            state="disabled" if status is None else "normal",
        )
        self._app_settings.configure(
            state="disabled" if read_app(status, self._app_settings_missing) is None else "normal"
        )

    def show_stopped(self, message: str) -> None:
        self._shown = None
        self._status.configure(text=message, foreground=DIM)
        self._hint.configure(text="", foreground=DIM)
        self._settings_for.configure(text="")
        for label in self._details:
            label.configure(text="")
        self._pause.configure(state="disabled")
        self._app_settings.configure(state="disabled")

    def _open_app_settings(self, on_read_app_settings: Callable[[str, str], None]) -> None:
        app = read_app(self._shown, self._app_settings_missing)
        if app is not None:
            on_read_app_settings(*app)

    def _pause_hint(self) -> str:
        return "Read lines aloud again." if self._paused else "Stop reading lines aloud until you resume."
