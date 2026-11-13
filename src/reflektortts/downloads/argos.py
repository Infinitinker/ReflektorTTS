"""Translation models from Argos Translate's published package index.

The index gives each model's languages and download link only: no license, size or checksum. The
size is asked from the server; the license is unknown until the model is downloaded (it is in the
package), so the page to read about the models is shown instead.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reflektortts.downloads import http
from reflektortts.downloads.cache import cached, save
from reflektortts.downloads.source import DownloadError, DownloadPlugin, Entry, Kind, Progress
from reflektortts.languages import ALIASES, LANGUAGES, primary_language
from reflektortts.stages.translate.model import (
    ModelInstallError,
    Pair,
    install_archive,
    installed_model,
    models_dir,
    remove_model,
)
from reflektortts.staging import remove_leftovers, staging_folder

NAME = "argos"
TITLE = "Argos Translate"
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
        remove_leftovers(models or models_dir())

    def entries(self, refresh: bool) -> list[Entry]:
        packages = self._index(refresh)
        sizes = self._sizes(packages, refresh)
        return [
            Entry(
                id=f"{NAME}:{pair[0]}-{pair[1]}",
                source_title=TITLE,
                kind=Kind.TRANSLATION,
                name=f"{LANGUAGES[pair[0]].english_name} → {LANGUAGES[pair[1]].english_name}",
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
        with staging_folder(self._models or models_dir()) as staging:
            archive = Path(staging) / "package.argosmodel"
            self._download(package["links"][0], archive, progress)
            try:
                install_archive(archive, pair, self._models)
            except ModelInstallError as error:
                raise DownloadError(str(error)) from error

    def remove(self, entry: Entry) -> None:
        remove_model(_pair(entry), self._models)

    def _index(self, refresh: bool) -> dict[Pair, dict[str, Any]]:
        """The translation models between two languages ReflektorTTS knows, by language pair. A
        package under a code that is an alias here (Argos' "pb" and "zt") is listed under the
        language's code, unless the index has a package under that code too."""
        data = cached(self._cache / "index.json", lambda: self._fetch(INDEX_URL), refresh)
        packages: dict[Pair, dict[str, Any]] = {}
        try:
            for package in sorted(json.loads(data), key=_under_alias):
                pair = primary_language(package["from_code"]), primary_language(package["to_code"])
                if pair[0] in LANGUAGES and pair[1] in LANGUAGES and pair[0] != pair[1] and package.get("links"):
                    packages.setdefault(pair, package)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise DownloadError(
                f"The list of Argos translation models is not in the expected format ({error})."
            ) from error
        return packages

    def _sizes(self, packages: dict[Pair, dict[str, Any]], refresh: bool) -> dict[str, int]:
        """Each model's size by link, as its server reports it; asked once per link and kept."""
        path = self._cache / "sizes.json"
        sizes: dict[str, int] = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        if path.is_file() and not refresh:
            return sizes
        links = [link for package in packages.values() if (link := package["links"][0]) not in sizes]
        asked = {link: size for link, size in zip(links, http.each(self._size, links), strict=True) if size is not None}
        if asked:
            save(path, json.dumps(sizes | asked).encode("utf-8"))
        return sizes | asked


def _under_alias(package: dict[str, Any]) -> bool:
    return package["from_code"] in ALIASES or package["to_code"] in ALIASES


def _pair(entry: Entry) -> Pair:
    return entry.languages[0], entry.languages[1]


PLUGIN = DownloadPlugin(name=NAME, create=ArgosModels)
