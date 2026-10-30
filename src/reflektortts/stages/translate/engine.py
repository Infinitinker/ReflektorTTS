"""Runs a downloaded model with CTranslate2, tokenized the way it was trained: Moses tokens split into BPE subwords."""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

# Polish declines foreign names with an apostrophe ("Frenzy'ego", "Joe'go"); the Moses
# detokenizer leaves a space before it. Only these endings are joined, so quotes stay apart.
_NAME_ENDING = re.compile(r"(?<=\w) '(?=(?:ego|go|emu|mu|em|m|a|u|ie|owi|y|ów|om|ami|ach)\b)")


def join_name_endings(text: str) -> str:
    return _NAME_ENDING.sub("'", text)


class Engine(Protocol):
    def translate(self, sentences: Sequence[str]) -> str:
        """Translates the sentences of one line and joins them back into a line."""


class TranslationUnavailableError(Exception):
    """The optional translation packages are not installed."""


class MosesBpeEngine:
    """Translates on the CPU with an int8 model, using the decoding settings of Argos Translate."""

    def __init__(self, model_dir: Path, source: str, target: str) -> None:
        try:
            import ctranslate2
            from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
            from subword_nmt.apply_bpe import BPE
        except ImportError as error:
            raise TranslationUnavailableError(
                "Translation needs the translate extra: pip install reflektortts[translate]"
            ) from error

        self._translator = ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="int8")
        self._normalizer = MosesPunctNormalizer(source)
        self._tokenizer = MosesTokenizer(source)
        self._detokenizer = MosesDetokenizer(target)
        with (model_dir / "bpe.model").open(encoding="utf-8") as codes:
            self._bpe = BPE(codes)

    def translate(self, sentences: Sequence[str]) -> str:
        batch = [self._encode(sentence) for sentence in sentences]
        results = self._translator.translate_batch(batch, beam_size=4, length_penalty=0.2, replace_unknowns=True)
        tokens = [token for result in results for token in result.hypotheses[0]]
        words = " ".join(tokens).replace("@@ ", "").split(" ")
        return join_name_endings(str(self._detokenizer.detokenize(words)))

    def _encode(self, sentence: str) -> list[str]:
        words = self._tokenizer.tokenize(self._normalizer.normalize(sentence))
        return list(self._bpe.segment_tokens(words))
