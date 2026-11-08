"""The medals the Profiles tab shows a profile's rating with: a disc in the medal's color, or a
gray ring for a profile that is not rated."""

import base64
import io
import tkinter as tk

from PIL import Image, ImageDraw

MEDALS = {
    "bronze": ("#cd7f32", "#8a5522"),
    "silver": ("#c8c8c8", "#7d7d7d"),
    "gold": ("#e6b422", "#94700f"),
    "platinum": ("#b4c7dc", "#5f7891"),
}
"""Each medal's fill and rim, by its rating's name in a profile."""
UNRATED_RIM = "#a0a0a0"
SUPERSAMPLING = 4
"""Drawn this many times larger, then scaled down, for smooth edges."""
GAP = 4
"""Empty pixels right of the medal, which Tkinter puts right before the text."""


def medal_image(rating: str | None, size: int) -> Image.Image:
    """The medal for a rating, or the ring for None, size pixels high, with GAP more pixels
    of room to its right."""
    big = size * SUPERSAMPLING
    image = Image.new("RGBA", (big + GAP * SUPERSAMPLING, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = (SUPERSAMPLING, SUPERSAMPLING, big - SUPERSAMPLING - 1, big - SUPERSAMPLING - 1)
    if rating is None:
        draw.ellipse(box, outline=UNRATED_RIM, width=SUPERSAMPLING * 2)
    else:
        fill, rim = MEDALS[rating]
        draw.ellipse(box, fill=fill, outline=rim, width=SUPERSAMPLING)
    return image.resize((size + GAP, size), Image.Resampling.LANCZOS)


def medal_photo(rating: str | None, size: int) -> tk.PhotoImage:
    """The medal as a Tkinter image (Tkinter must be running); keep a reference to it, or Tkinter
    drops it."""
    png = io.BytesIO()
    medal_image(rating, size).save(png, "PNG")
    return tk.PhotoImage(data=base64.b64encode(png.getvalue()))
