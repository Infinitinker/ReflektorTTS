"""What the desktop app shows of the downloads: entries, their state, sizes and the summary."""

import pytest

from reflektortts.desktop.api.catalog import (
    OTHER_VOICE_LICENSE,
    DownloadItem,
    DownloadList,
    other_voices,
    parse_list,
    size_text,
    state_text,
    summary_text,
)


def test_a_listing_from_the_api_becomes_items() -> None:
    data = {
        "entries": [
            {
                "id": "argos:en-pl",
                "source_title": "Argos Translate",
                "kind": "translation",
                "name": "English → Polish",
                "languages": ["en", "pl"],
                "size": 67_108_864,
                "license": None,
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
                "Argos Translate",
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


def test_the_summary_counts_the_installed_entries() -> None:
    def item(state: str) -> DownloadItem:
        return DownloadItem(
            "id", "voice", "Voice", ("en",), None, None, "https://example.invalid", state, 0, None, "Piper"
        )

    assert summary_text([item("installed"), item("available"), item("downloading")]) == "Installed: 1 of 3"


def test_installed_voices_that_are_not_downloads_are_listed_but_not_removable() -> None:
    gosia = DownloadItem(
        "piper:pl_PL-gosia-medium",
        "voice",
        "pl_PL-gosia-medium",
        ("pl",),
        63,
        None,
        "https://x.invalid",
        "installed",
        0,
        None,
        "Piper",
    )
    voices = {
        "voices": [
            {
                "id": "piper:pl_PL-gosia-medium",
                "engine": "piper",
                "name": "pl_PL-gosia-medium",
                "language": "pl-PL",
                "engine_title": "Piper",
                "installed_note": None,
            },
            {
                "id": "windows:Microsoft Adam",
                "engine": "windows",
                "name": "Microsoft Adam",
                "language": "pl-PL",
                "engine_title": "Windows",
                "installed_note": "Comes with Windows: add or remove them in Settings.",
            },
            {
                "id": "windows:Microsoft Hedda",
                "engine": "windows",
                "name": "Microsoft Hedda",
                "language": "de-DE",
                "engine_title": "Windows",
                "installed_note": "Comes with Windows: add or remove them in Settings.",
            },
        ]
    }

    [adam] = other_voices(voices, [gosia], languages={"en", "pl"})

    assert (adam.id, adam.source, adam.languages, adam.state, adam.removable, adam.page) == (
        "windows:Microsoft Adam",
        "Windows",
        ("pl",),
        "installed",
        False,
        "",
    )
    assert adam.license == "Comes with Windows: add or remove them in Settings."


def test_an_installed_voice_whose_engine_says_nothing_about_it_is_installed_outside_reflektortts() -> None:
    voices = {
        "voices": [
            {
                "id": "piper:pl_PL-darkman-medium",
                "engine": "piper",
                "name": "pl_PL-darkman-medium",
                "language": "pl-PL",
                "engine_title": "Piper",
                "installed_note": None,
            }
        ]
    }

    [darkman] = other_voices(voices, [], languages={"pl"})

    assert darkman.license == OTHER_VOICE_LICENSE
