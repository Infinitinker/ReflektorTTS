"""Translation models from Argos Translate's published package index.

The index gives each model's languages and download link only: no license, size or checksum. The
size is asked from the server; the license is unknown until the model is downloaded (it is in the
package), so the page to read about the models is shown instead.
"""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reflektortts.downloads import http
from reflektortts.downloads.cache import cached, save
from reflektortts.downloads.source import DownloadError, DownloadPlugin, Entry, Kind, Progress
from reflektortts.languages import LANGUAGES
from reflektortts.stages.translate.model import ModelInstallError, Pair, install_archive, installed_model, remove_model

NAME = "argos"
INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
PAGE_URL = "https://www.argosopentech.com/argospm/index/"


class ArgosModels:
    def __init__(
        self,
        cache: Path,
        models: Path | None = None,
        fetch: Callable[[str], bytes] = http.fetch,
        download: Callable[[str, Path, Progress], None] = http.download,
        size: Callable[[str], int | None] = http.content_length,
    ) -> None:
        self._cache = cache
        self._models = models
        self._fetch = fetch
        self._download = download
        self._size = size

    def entries(self, refresh: bool) -> list[Entry]:
        packages = self._index(refresh)
        sizes = self._sizes(packages, refresh)
        return [
            Entry(
                id=f"{NAME}:{pair[0]}-{pair[1]}",
                kind=Kind.TRANSLATION,
                name=f"{package['from_name']} → {package['to_name']}",
                languages=pair,
                size=sizes.get(package["links"][0]),
                license=None,
                page=PAGE_URL,
                installed=installed_model(pair, self._models) is not None,
            )
            for pair, package in sorted(packages.items())
        ]

    def download(self, entry: Entry, progress: Progress) -> None:
        pair = _pair(entry)
        package = self._index(refresh=False)[pair]
        with tempfile.TemporaryDirectory() as staging:
            archive = Path(staging) / "package.argosmodel"
            self._download(package["links"][0], archive, progress)
            try:
                install_archive(archive, pair, self._models)
            except ModelInstallError as error:
                raise DownloadError(str(error)) from error

    def remove(self, entry: Entry) -> None:
        remove_model(_pair(entry), self._models)

    def _index(self, refresh: bool) -> dict[Pair, dict[str, Any]]:
        """The translation models between languages ReflektorTTS supports, by language pair."""
        data = cached(self._cache / "index.json", lambda: self._fetch(INDEX_URL), refresh)
        try:
            return {
                (package["from_code"], package["to_code"]): package
                for package in json.loads(data)
                if package["from_code"] in LANGUAGES
                and package["to_code"] in LANGUAGES
                and package["from_code"] != package["to_code"]
                and package.get("links")
            }
        except (ValueError, KeyError, TypeError) as error:
            raise DownloadError(
                f"The list of Argos translation models is not in the expected format ({error})."
            ) from error

    def _sizes(self, packages: dict[Pair, dict[str, Any]], refresh: bool) -> dict[str, int]:
        """Each model's size by link, as its server reports it; asked once per link and kept."""
        path = self._cache / "sizes.json"
        sizes: dict[str, int] = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        asked = False
        for package in packages.values():
            link = package["links"][0]
            if link in sizes or not refresh and path.is_file():
                continue
            size = self._size(link)
            if size is not None:
                sizes[link] = size
                asked = True
        if asked:
            save(path, json.dumps(sizes).encode("utf-8"))
        return sizes


def _pair(entry: Entry) -> Pair:
    return entry.languages[0], entry.languages[1]


PLUGIN = DownloadPlugin(name=NAME, create=ArgosModels)
