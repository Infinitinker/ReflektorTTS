"""The translate stage plugin: translates lines into the output language (lektor mode)."""

import functools
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping
from dataclasses import replace
from typing import Any

from reflektortts.events import TextEvent
from reflektortts.glossary import Glossary
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import StagePlugin, load_schema
from reflektortts.stages.translate.engine import Engine, load_engine
from reflektortts.stages.translate.glossary import GlossaryRules
from reflektortts.stages.translate.model import ModelNotInstalledError, installed_model
from reflektortts.stages.translate.sentences import split_sentences

logger = logging.getLogger(__name__)

CACHE_SIZE = 256

type Pair = tuple[str, str]
type Recent = OrderedDict[tuple[Pair, Hashable, str], str]
"""Translations by language pair, glossary and line."""
DEFAULT_MIN_LETTERS = 1


class Translate:
    """Translates each line from the input language into its output language, sentence by sentence.

    It runs only for pairs inactive_reason accepts. A pair's engine is opened the first time a line
    needs it. The profile's glossary keeps terms untranslated or gives them a meaning, and a line
    with fewer than min_letters letters besides its kept and spoken terms (e.g. only names) is left
    as written. Recent translations are remembered, since apps repeat lines and each line is
    processed once for the text shown and once for speech.
    """

    def __init__(
        self,
        open_engine: Callable[[str, str], Engine],
        cache: Recent | None = None,
        glossary: GlossaryRules | None = None,
        min_letters: int = DEFAULT_MIN_LETTERS,
    ) -> None:
        self._open_engine = open_engine
        self._engines: dict[Pair, Engine] = {}
        self._cache: Recent = OrderedDict() if cache is None else cache
        self._glossary = GlossaryRules(()) if glossary is None else glossary
        self._min_letters = min_letters

    def process(self, event: TextEvent) -> TextEvent | None:
        if not event.text or self._glossary.letters_besides_terms(event.text) < self._min_letters:
            return event
        return replace(event, text=self._translate((event.input_language, event.output_language), event.text))

    def _translate(self, pair: Pair, text: str) -> str:
        key = (pair, self._glossary.key, text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if pair not in self._engines:
            self._engines[pair] = self._open_engine(*pair)
        prepared = self._glossary.prepare(text)
        translated = prepared.put_back(self._engines[pair].translate(split_sentences(prepared.text)))
        self._cache[key] = translated
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return translated


NO_MODEL = "No translation model for these languages"


@functools.cache
def open_engine(source: str, target: str) -> Engine:
    """Loads the pair's installed model, once: every translate stage, of every source and app,
    shares the loaded model. A failed load is tried again next time.
    """
    model_dir = installed_model((source, target))
    if model_dir is None:
        raise ModelNotInstalledError(NO_MODEL)
    started = time.perf_counter()
    engine = load_engine(model_dir, source, target)
    logger.info("Loaded the %s-%s translation model in %.1f s", source, target, time.perf_counter() - started)
    return engine


def inactive_reason(languages: Languages) -> str | None:
    """Models are never downloaded here: only an installed one is used."""
    if languages.input == languages.output:
        return "Input and output language are the same"
    if installed_model((languages.input, languages.output)) is None:
        return NO_MODEL
    return None


RECENT: Recent = OrderedDict()
"""Recent translations shared by every translate stage; they all run on the one runner thread."""


def create(settings: Mapping[str, Any], glossary: Glossary) -> Translate:
    return Translate(open_engine, RECENT, GlossaryRules(glossary), settings.get("min_letters", DEFAULT_MIN_LETTERS))


PLUGIN = StagePlugin(
    type="translate",
    settings_schema=load_schema("reflektortts.stages.translate", "translate.schema.json"),
    create=create,
    summary="Translates into the output language",
    inactive_reason=inactive_reason,
)
