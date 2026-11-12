"""The theme's check for Tk drawing its fonts without Xft."""

import tkinter as tk
from types import SimpleNamespace
from typing import Any, cast

import pytest

from reflektortts.desktop.widgets.theme import draws_without_xft


def root(windowing_system: str, font_system: str | None) -> tk.Misc:
    """A Tk root that answers what draws_without_xft asks; None: a Tk too old to tell its font system."""

    def call(*command: str) -> str:
        if command == ("tk", "windowingsystem"):
            return windowing_system
        if font_system is None:
            raise tk.TclError("key not known")
        return font_system

    fake: Any = SimpleNamespace(tk=SimpleNamespace(call=call))
    return cast(tk.Misc, fake)


@pytest.mark.parametrize(
    ("windowing_system", "font_system", "expected"),
    [("x11", "x11", True), ("x11", "xft", False), ("win32", "", False), ("x11", None, False)],
)
def test_only_x11_without_xft_draws_without_xft(windowing_system: str, font_system: str | None, expected: bool) -> None:
    assert draws_without_xft(root(windowing_system, font_system)) is expected
