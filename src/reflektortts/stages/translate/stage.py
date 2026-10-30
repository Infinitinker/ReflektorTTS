"""The translate stage plugin: translates lines into the speech language (lektor mode)."""

import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Collection, Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.languages import AUTO
from reflektortts.pipeline.plugins import StagePlugin, load_schema
from reflektortts.stages.translate.engine import Engine, MosesBpeEngine
from reflektortts.stages.translate.model import PACKAGES, ensure_model
from reflektortts.stages.translate.sentences import split_sentences

logger = logging.getLogger(__name__)

AUTO_MEANS = "en"
"""The game language assumed for "auto"; English is the only source language with a model."""
CACHE_SIZE = 256

type Pair = tuple[str, str]


class Translate:
    """Translates each line from the game language into its speech language, sentence by sentence.

    Lines already in the speech language, and pairs without a model, pass unchanged. A pair's
    engine is opened the first time a line needs it. Recent translations are remembered, since
    games repeat lines.
    """

    def __init__(self, pairs: Collection[Pair], open_engine: Callable[[str, str], Engine]) -> None:
        self._pairs = pairs
        self._open_engine = open_engine
        self._engines: dict[Pair, Engine] = {}
        self._cache: OrderedDict[tuple[Pair, str], str] = OrderedDict()

    def process(self, event: TextEvent) -> TextEvent | None:
        source = AUTO_MEANS if event.game_language == AUTO else event.game_language
        pair = (source, event.speech_language)
        if not event.text or source == event.speech_language:
            return event
        if pair not in self._pairs:
            logger.debug("No translation model from %s to %s", *pair)
            return event
        return replace(event, text=self._translate(pair, event.text))

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


def open_engine(source: str, target: str) -> Engine:
    """Downloads the pair's model if needed and loads it."""
    model_dir = ensure_model(PACKAGES[(source, target)])
    started = time.perf_counter()
    engine = MosesBpeEngine(model_dir, source, target)
    logger.info("Loaded the %s-%s translation model in %.1f s", source, target, time.perf_counter() - started)
    return engine


def create(settings: Mapping[str, Any]) -> Translate:
    return Translate(PACKAGES.keys(), open_engine)


PLUGIN = StagePlugin(
    type="translate",
    settings_schema=load_schema("reflektortts.stages.translate", "translate.schema.json"),
    create=create,
    summary="Translates into the speech language",
)
