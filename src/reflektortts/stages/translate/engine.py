"""Runs a downloaded model with CTranslate2, tokenized the way it was trained: Moses tokens split
into BPE subwords (bpe.model), or SentencePiece pieces (sentencepiece.model), as Argos Translate's
packages come."""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

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


UNAVAILABLE = "Translation needs the translate extra: pip install reflektortts[translate]"
BPE_FILE = "bpe.model"
SENTENCEPIECE_FILE = "sentencepiece.model"


def load_engine(model_dir: Path, source: str, target: str) -> Engine:
    """The engine for a model, by the tokenizer it came with."""
    if (model_dir / SENTENCEPIECE_FILE).is_file():
        return SentencePieceEngine(model_dir)
    return MosesBpeEngine(model_dir, source, target)


def _translator(model_dir: Path) -> Any:
    """Translates on the CPU with an int8 model."""
    try:
        import ctranslate2
    except ImportError as error:
        raise TranslationUnavailableError(UNAVAILABLE) from error
    return ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="int8")


def _best(translator: Any, batch: list[list[str]]) -> list[list[str]]:
    """Each sentence's best translation, with the decoding settings of Argos Translate."""
    results = translator.translate_batch(batch, beam_size=4, length_penalty=0.2, replace_unknowns=True)
    return [list(result.hypotheses[0]) for result in results]


class SentencePieceEngine:
    def __init__(self, model_dir: Path) -> None:
        try:
            import sentencepiece
        except ImportError as error:
            raise TranslationUnavailableError(UNAVAILABLE) from error
        self._translator = _translator(model_dir)
        self._pieces = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / SENTENCEPIECE_FILE))

    def translate(self, sentences: Sequence[str]) -> str:
        batch = [self._pieces.encode(sentence, out_type=str) for sentence in sentences]
        return join_name_endings(" ".join(self._pieces.decode(tokens) for tokens in _best(self._translator, batch)))


class MosesBpeEngine:
    def __init__(self, model_dir: Path, source: str, target: str) -> None:
        try:
            from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
            from subword_nmt.apply_bpe import BPE
        except ImportError as error:
            raise TranslationUnavailableError(UNAVAILABLE) from error

        self._translator = _translator(model_dir)
        self._normalizer = MosesPunctNormalizer(source)
        self._tokenizer = MosesTokenizer(source)
        self._detokenizer = MosesDetokenizer(target)
        with (model_dir / BPE_FILE).open(encoding="utf-8") as codes:
            self._bpe = BPE(codes)

    def translate(self, sentences: Sequence[str]) -> str:
        batch = [self._encode(sentence) for sentence in sentences]
        tokens = [token for sentence in _best(self._translator, batch) for token in sentence]
        words = " ".join(tokens).replace("@@ ", "").split(" ")
        return join_name_endings(str(self._detokenizer.detokenize(words)))

    def _encode(self, sentence: str) -> list[str]:
        words = self._tokenizer.tokenize(self._normalizer.normalize(sentence))
        return list(self._bpe.segment_tokens(words))
