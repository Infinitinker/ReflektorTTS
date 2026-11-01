"""What the desktop app shows of the downloads: entries, their state and progress, from the API,
and the voices installed by other means."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from reflektortts.languages import primary_language

MB = 1024 * 1024
OTHER_VOICE_LICENSES = {
    "windows": "Comes with Windows: add or remove Windows voices in Settings > Time & language > Speech.",
}
"""In place of a license, where a voice installed by other means comes from, by its engine."""
OTHER_VOICE_LICENSE = "Installed outside ReflektorTTS."


@dataclass(frozen=True)
class DownloadItem:
    id: str
    kind: str
    """As the API names it, e.g. "voice" or "translation"."""
    name: str
    languages: tuple[str, ...]
    size: int | None
    license: str | None
    page: str
    state: str
    """"available", "downloading" or "installed"."""
    done: int
    total: int | None
    source: str
    """Where it comes from, as shown to users, e.g. "Piper" or "Windows"."""
    removable: bool = True
    """False for a voice installed by other means, e.g. one that comes with Windows."""


@dataclass(frozen=True)
class DownloadList:
    items: tuple[DownloadItem, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class DownloadProgress:
    """A download event: state is "downloading", "installed", "failed" or "removed"."""

    id: str
    state: str
    done: int
    total: int | None
    message: str


def parse_list(data: Mapping[str, Any]) -> DownloadList:
    """The answer to GET /v1/downloads."""
    items = tuple(
        DownloadItem(
            id=entry["id"],
            kind=entry["kind"],
            name=entry["name"],
            languages=tuple(entry["languages"]),
            size=entry["size"],
            license=entry["license"],
            page=entry["page"],
            state=entry["state"],
            done=entry["done"],
            total=entry["total"],
            source=entry["source_title"],
        )
        for entry in data["entries"]
    )
    return DownloadList(items, tuple(data["errors"]))


def other_voices(
    voices: Mapping[str, Any], downloads: Sequence[DownloadItem], languages: Collection[str]
) -> list[DownloadItem]:
    """The installed voices in GET /v1/voices that are not downloads (a voice download's ID is
    its voice's), in the given languages: listed as installed, but they cannot be removed here."""
    listed = {item.id for item in downloads}
    return [
        DownloadItem(
            id=voice["id"],
            kind="voice",
            name=voice["name"],
            languages=(primary_language(voice["language"]),),
            size=None,
            license=OTHER_VOICE_LICENSES.get(voice["engine"], OTHER_VOICE_LICENSE),
            page="",
            state="installed",
            done=0,
            total=None,
            source=voice["engine_title"],
            removable=False,
        )
        for voice in voices["voices"]
        if voice["id"] not in listed and primary_language(voice["language"]) in languages
    ]


@dataclass(frozen=True)
class PreviewState:
    """A preview event: a voice's preview started (playing, also while the voice loads) or ended."""

    voice: str
    playing: bool


def parse_preview(event: Mapping[str, Any]) -> PreviewState | None:
    """The preview event in an /v1/events message, or None for other events."""
    if event.get("type") != "preview":
        return None
    return PreviewState(event["voice"], event["playing"])


def parse_progress(event: Mapping[str, Any]) -> DownloadProgress | None:
    """The download event in an /v1/events message, or None for other events."""
    if event.get("type") != "download":
        return None
    return DownloadProgress(event["id"], event["state"], event["done"], event["total"], event["message"])


def size_text(size: int | None) -> str:
    return "" if size is None else f"{size / MB:.0f} MB"


def summary_text(items: Sequence[DownloadItem]) -> str:
    installed = sum(item.state == "installed" for item in items)
    return f"{installed} of {len(items)} installed"


def state_text(state: str, done: int = 0, total: int | None = None) -> str:
    """A row's state column: empty when it can be downloaded."""
    if state == "installed":
        return "Installed"
    if state == "downloading":
        return f"Downloading {done * 100 // total}%" if total else "Downloading"
    return ""
