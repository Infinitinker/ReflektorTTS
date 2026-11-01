import pytest

from reflektortts.desktop.catalog import DownloadItem, DownloadList, parse_list, size_text, state_text


def test_a_listing_from_the_api_becomes_items() -> None:
    data = {
        "entries": [
            {
                "id": "argos:en-pl",
                "kind": "translation",
                "name": "English → Polish",
                "languages": ["en", "pl"],
                "size": 67_108_864,
                "licence": None,
                "page": "https://example.invalid",
                "state": "installed",
                "done": 0,
                "total": None,
            }
        ],
        "errors": ["Could not reach the Piper list."],
    }

    assert parse_list(data) == DownloadList(
        (
            DownloadItem(
                "argos:en-pl",
                "translation",
                "English → Polish",
                ("en", "pl"),
                67_108_864,
                None,
                "https://example.invalid",
                "installed",
                0,
                None,
            ),
        ),
        ("Could not reach the Piper list.",),
    )


@pytest.mark.parametrize(
    ("state", "done", "total", "text"),
    [
        ("available", 0, None, ""),
        ("installed", 0, None, "Installed"),
        ("downloading", 25, 100, "Downloading 25%"),
        ("downloading", 25, None, "Downloading"),
    ],
)
def test_the_state_column(state: str, done: int, total: int | None, text: str) -> None:
    assert state_text(state, done, total) == text


def test_sizes_are_shown_in_megabytes() -> None:
    assert (size_text(63_205_000), size_text(None)) == ("60 MB", "")
