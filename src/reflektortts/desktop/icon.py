"""The app's icon, drawn by tools/draw_icon.py: one size of it at a time."""

import base64
import io
import tkinter as tk
from importlib import resources

from PIL import Image
from PIL.IcoImagePlugin import IcoFile

ICON = "icon.ico"


def icon_image(size: int) -> Image.Image:
    """The icon at one of the sizes the .ico holds (16 to 256 px)."""
    with resources.files("reflektortts.desktop").joinpath(ICON).open("rb") as file:
        return IcoFile(file).getimage((size, size)).convert("RGBA")


def icon_photo(size: int) -> tk.PhotoImage:
    """The icon as a Tkinter image (Tkinter must be running); keep a reference to it, or Tkinter
    drops it."""
    png = io.BytesIO()
    icon_image(size).save(png, "PNG")
    return tk.PhotoImage(data=base64.b64encode(png.getvalue()))
