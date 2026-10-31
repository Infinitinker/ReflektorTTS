"""Draws ReflektorTTS's icon into src/reflektortts/desktop/icon.ico.

A studio microphone in a shock mount with a pop filter, lit from behind by a round spotlight in
the overlay's warning orange; transparent outside the light. At 32 px and less the details would
blur, so those sizes show only the microphone, bolder and with a lighter head.

Run from the repository root after changing the drawing: python tools/draw_icon.py
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

OUTPUT = Path("src/reflektortts/desktop/icon.ico")
SIZES = (16, 24, 32, 48, 64, 128, 256)
SMALL = 32
"""Sizes up to this one get the simple drawing."""

S = 1024
"""Drawn at this size, then scaled down."""
CENTER = (512, 512)
RADIUS = 500
BLACK = (14, 14, 17, 255)
FABRIC = (24, 24, 28, 255)
GRILLE = (118, 120, 128, 255)
GRILLE_MESH = (62, 64, 72, 255)
SMALL_HEAD = (160, 162, 170, 255)
RIM = (255, 226, 170, 255)
HOT = (255, 222, 150)
WARNING = (255, 191, 77)
"""kWarningColor of the overlay's panel, ImVec4(1.0, 0.75, 0.3)."""
EDGE = (232, 150, 40)


def spotlight() -> Image.Image:
    """The disc: lighter at the hot spot behind the microphone, warning orange, deeper at the edge."""
    image = Image.new("RGBA", (S, S), (*EDGE, 255))
    draw = ImageDraw.Draw(image)
    hot = (CENTER[0] - 40, CENTER[1] - 80)
    steps = 160
    for step in range(steps, 0, -1):
        t = step / steps
        r = int(RADIUS * 1.15 * t)
        if t < 0.35:
            color = tuple(int(HOT[i] + (WARNING[i] - HOT[i]) * t / 0.35) for i in range(3))
        else:
            color = tuple(int(WARNING[i] + (EDGE[i] - WARNING[i]) * ((t - 0.35) / 0.65) ** 2) for i in range(3))
        draw.ellipse((hot[0] - r, hot[1] - r, hot[0] + r, hot[1] + r), fill=(*color, 255))
    return image.filter(ImageFilter.GaussianBlur(6))


def rim(shape: Image.Image, width: int) -> Image.Image:
    """The part of a shape's outline the light from behind catches: mostly its top."""
    edge = ImageChops.subtract(shape, shape.filter(ImageFilter.MinFilter(width)))
    fade = Image.linear_gradient("L").resize((S, S)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return ImageChops.multiply(edge, fade.point(lambda v: min(255, int(v * 1.5))))


def layer(fill: tuple[int, int, int, int], shape: Image.Image, rim_width: int = 0) -> Image.Image:
    """shape filled with fill; rim_width (odd) adds the edge of light."""
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    image.paste(fill, (0, 0), shape)
    if rim_width:
        image.paste(RIM, (0, 0), rim(shape, rim_width))
    return image


def microphone() -> list[Image.Image]:
    """The microphone: grille head, black body, shock mount, and the clamp leaving the light."""
    body = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(body)
    draw.rounded_rectangle((548, 180, 762, 860), radius=100, fill=255)
    draw.rectangle((622, 860, 688, 1024), fill=255)

    head = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(head)
    draw.rounded_rectangle((548, 180, 762, 470), radius=100, fill=255)
    draw.rectangle((548, 380, 762, 470), fill=255)
    mesh = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(mesh)
    for offset in range(-300, 300, 26):
        draw.line(((548 + offset, 180), (548 + offset + 290, 470)), fill=255, width=6)
        draw.line(((762 - offset, 180), (762 - offset - 290, 470)), fill=255, width=6)
    mesh = ImageChops.multiply(mesh, head)

    mount = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(mount)
    for y in (520, 800):
        draw.ellipse((470, y - 46, 840, y + 46), outline=255, width=22)
    for x in (476, 834):
        draw.line(((x, 520), (x, 800)), fill=255, width=20)

    return [layer(BLACK, body, 13), layer(GRILLE, head), layer(GRILLE_MESH, mesh), layer(BLACK, mount)]


def pop_filter() -> list[Image.Image]:
    """A large round pop filter, slightly turned, in front of the microphone, on a gooseneck."""
    box = (120, 150, 560, 700)
    fabric = Image.new("L", (S, S), 0)
    ImageDraw.Draw(fabric).ellipse(box, fill=235)
    frame = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(frame)
    draw.ellipse(box, outline=255, width=34)
    draw.rounded_rectangle((316, 690, 372, 770), radius=14, fill=255)
    start, control, end = (344, 770), (360, 1000), (650, 960)
    points = [
        (
            (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t**2 * end[0],
            (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t**2 * end[1],
        )
        for t in (step / 40 for step in range(41))
    ]
    draw.line(points, fill=255, width=30, joint="curve")
    # Light catches only the outer edge of the disc.
    outline = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    outline.paste(RIM, (0, 0), rim(ImageChops.lighter(fabric.point(lambda v: 255 if v else 0), frame), 11))
    return [layer(FABRIC, fabric), layer(BLACK, frame), outline]


def simple_microphone() -> list[Image.Image]:
    """For small sizes: only the microphone, centred and bold, with a light head."""
    body = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(body)
    draw.rounded_rectangle((302, 90, 722, 800), radius=210, fill=255)
    draw.rectangle((452, 780, 572, 1024), fill=255)
    head = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(head)
    draw.rounded_rectangle((302, 90, 722, 470), radius=210, fill=255)
    draw.rectangle((302, 330, 722, 470), fill=255)
    return [layer(BLACK, body, 19), layer(SMALL_HEAD, head)]


def icon(simple: bool) -> Image.Image:
    image = spotlight()
    # Drawn with the pop filter on the left, then mirrored: microphone left, pop filter right.
    for part in simple_microphone() if simple else [*microphone(), *pop_filter()]:
        image = Image.alpha_composite(image, ImageOps.mirror(part))
    # A slightly darker edge, so the circle reads on light backgrounds too.
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(
        (CENTER[0] - RADIUS, CENTER[1] - RADIUS, CENTER[0] + RADIUS, CENTER[1] + RADIUS),
        outline=(*(max(0, c - 40) for c in EDGE), 255),
        width=14,
    )
    image = Image.alpha_composite(image, ring)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        (CENTER[0] - RADIUS, CENTER[1] - RADIUS, CENTER[0] + RADIUS, CENTER[1] + RADIUS), fill=255
    )
    image.putalpha(mask)
    return image


def main() -> None:
    detailed, simple = icon(simple=False), icon(simple=True)
    images = [(simple if size <= SMALL else detailed).resize((size, size), Image.Resampling.LANCZOS) for size in SIZES]
    largest = images[-1]
    largest.save(OUTPUT, sizes=[(size, size) for size in SIZES], append_images=images[:-1])
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
