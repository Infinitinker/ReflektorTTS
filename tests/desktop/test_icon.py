"""The app's icon: each size the app uses, round with a transparent outside."""

import pytest

from reflektortts.desktop.icon import icon_image


@pytest.mark.parametrize("size", [16, 32, 48, 256])
def test_the_icon_comes_in_each_size_the_app_uses(size: int) -> None:
    image = icon_image(size)

    assert image.size == (size, size)
    assert image.mode == "RGBA"


def test_the_icon_is_round_with_a_transparent_outside() -> None:
    image = icon_image(256)

    assert image.getpixel((0, 0))[3] == 0  # type: ignore[index]
    assert image.getpixel((128, 128))[3] == 255  # type: ignore[index]
