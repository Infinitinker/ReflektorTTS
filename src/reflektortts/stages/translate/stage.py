"""The translate stage plugin: translates lines into the output language (lektor mode)."""

import functools
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import StagePlugin, load_schema
from reflektortts.stages.translate.engine import Engine, MosesBpeEngine
from reflektortts.stages.translate.model import PACKAGES, ensure_model
from reflektortts.stages.translate.sentences import split_sentences

logger = logging.getLogger(__name__)

CACHE_SIZE = 256

type Pair = tuple[str, str]


class Translate:
    """Translates each line from the game language into its output language, sentence by sentence.

    It runs only for pairs inactive_reason accepts. A pair's engine is opened the first time a line
    needs it. Recent translations are remembered, since games repeat lines.
    """

    def __init__(self, open_engine: Callable[[str, str], Engine]) -> None:
        self._open_engine = open_engine
        self._engines: dict[Pair, Engine] = {}
        self._cache: OrderedDict[tuple[Pair, str], str] = OrderedDict()

    def process(self, event: TextEvent) -> TextEvent | None:
        if not event.text:
            return event
        return replace(event, text=self._translate((event.game_language, event.output_language), event.text))

    def _translate(self, pair: Pair, text: str) -> str:
        key = (pair, text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if pair not in self._engines:
            self._engines[pair] = self._open_engine(*pair)
        translated = self._engines[pair].translate(split_sentences(text))
        self._cache[key] = translated
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return translated


@functools.cache
def open_engine(source: str, target: str) -> Engine:
    """Downloads the pair's model if needed and loads it, once: every translate stage, of every
    source and game, shares the loaded model. A failed download or load is tried again next time.
    """
    model_dir = ensure_model(PACKAGES[(source, target)])
    started = time.perf_counter()
    engine = MosesBpeEngine(model_dir, source, target)
    logger.info("Loaded the %s-%s translation model in %.1f s", source, target, time.perf_counter() - started)
    return engine


def inactive_reason(languages: Languages) -> str | None:
    if languages.game == languages.output:
        return "Game and output language are the same"
    if (languages.game, languages.output) not in PACKAGES:
        return "No translation between these languages yet"
    return None


def create(settings: Mapping[str, Any]) -> Translate:
    return Translate(open_engine)


PLUGIN = StagePlugin(
    type="translate",
    settings_schema=load_schema("reflektortts.stages.translate", "translate.schema.json"),
    create=create,
    summary="Translates into the output language",
    inactive_reason=inactive_reason,
)
