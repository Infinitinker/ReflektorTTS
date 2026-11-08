from reflektortts.desktop.medals import GAP, medal_image


def alpha(rating: str | None, x: int, y: int) -> int:
    pixel = medal_image(rating, 16).getpixel((x, y))
    assert isinstance(pixel, tuple)
    return int(pixel[3])


def test_a_medal_is_a_disc_in_its_color_with_room_after_it() -> None:
    image = medal_image("gold", 16)

    assert image.size == (16 + GAP, 16)
    assert image.getpixel((8, 8)) == (230, 180, 34, 255)
    assert alpha("gold", 16 + GAP - 1, 8) == 0


def test_a_profile_that_is_not_rated_gets_an_empty_ring() -> None:
    assert alpha(None, 8, 8) == 0
    assert alpha(None, 2, 8) > 0


def test_each_medal_has_a_color_of_its_own_and_none_looks_unrated() -> None:
    centers = [medal_image(rating, 16).getpixel((8, 8)) for rating in ("bronze", "silver", "gold", "platinum")]

    assert len(set(centers)) == 4
    assert all(center[3] == 255 and min(center[:3]) < 230 for center in centers)  # type: ignore[index]
