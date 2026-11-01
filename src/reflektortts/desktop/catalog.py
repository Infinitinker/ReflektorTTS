"""What the desktop app shows of the downloads: entries, their state and progress, from the API."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MB = 1024 * 1024


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
        )
        for entry in data["entries"]
    )
    return DownloadList(items, tuple(data["errors"]))


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
