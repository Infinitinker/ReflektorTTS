"""Runs a downloaded model with CTranslate2, tokenized the way it was trained: Moses tokens split
into BPE subwords (bpe.model), or SentencePiece pieces (sentencepiece.model), as Argos Translate's
packages come."""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from reflektortts.letters import ends_in_letter


class Engine(Protocol):
    def translate(self, sentences: Sequence[str]) -> str:
        """Translates the sentences of one line and joins them back into a line."""


BPE_FILE = "bpe.model"
SENTENCEPIECE_FILE = "sentencepiece.model"
MIN_SHOUTED_LETTERS = 2
WORD_MARK = "▁"
"""SentencePiece's mark for the start of a word."""


FULL_STOPS = {"ja": "。", "zh": "。"}
"""The full stop a language ends a sentence with, where it is not "."; these languages have no
space after it."""
ANY_FULL_STOP = ".。।۔։።။།។"
"""The full stops of the scripts translations come in, any of which the full stop added to a
sentence may be translated as."""


def load_engine(model_dir: Path, source: str, target: str) -> Engine:
    """The engine for a model, by the tokenizer it came with."""
    if (model_dir / SENTENCEPIECE_FILE).is_file():
        return SentencePieceEngine(model_dir, source, target)
    return MosesBpeEngine(model_dir, source, target)


def join_sentences(sentences: Sequence[str], language: str) -> str:
    """Translated sentences as one line: with spaces between them, unless the language's full
    stop has none after it, as Chinese's has."""
    return ("" if language in FULL_STOPS else " ").join(sentences)


def _translator(model_dir: Path) -> Any:
    """Translates on the CPU, in the type the model was saved in: most models are int8, and a
    float32 one (Argos' Spanish to English 1.9) repeats one word forever when run as int8."""
    # Imported here, so the core starts without loading it until a line is translated.
    import ctranslate2

    return ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="default")


_PRONOUN_I = re.compile(r"\bi\b")


def is_shouted(sentence: str) -> bool:
    """Whether every letter of the sentence is a capital, as in "GOODBYE!"."""
    letters = [character for character in sentence if character.isalpha()]
    return len(letters) >= MIN_SHOUTED_LETTERS and all(letter.isupper() for letter in letters)


def prepare(sentence: str, source: str) -> str:
    """The sentence as the model translates it best. The model copies some sentences instead of
    translating them: those in capitals, whose words it splits into fragments it does not know,
    so they are put in sentence case (keeping English "I"); and some with no ending, as lines an
    app splits across subtitles have, so they get the language's full stop."""
    if is_shouted(sentence):
        sentence = sentence[:1] + sentence[1:].lower()
        if source == "en":
            sentence = _PRONOUN_I.sub("I", sentence)
    return sentence + FULL_STOPS.get(source, ".") if ends_in_letter(sentence) else sentence


def restore(sentence: str, translated: str) -> str:
    """The translation of a prepared sentence, put back the way the sentence was written."""
    if ends_in_letter(sentence) and translated.endswith(tuple(ANY_FULL_STOP)) and not translated.endswith(".."):
        translated = translated[:-1]
    return translated.upper() if is_shouted(sentence) else translated


def join_pieces(text: str) -> str:
    """SentencePiece output with its word marks turned into spaces. Models converted from OPUS-MT
    come with the source language's SentencePiece model only, which leaves the marks of target
    words it does not know in the text ("la▁voiture")."""
    return " ".join(text.replace(WORD_MARK, " ").split())


def _best(translator: Any, batch: list[list[str]]) -> list[list[str]]:
    """Each sentence's best translation, with the decoding settings of Argos Translate."""
    results = translator.translate_batch(batch, beam_size=4, length_penalty=0.2, replace_unknowns=True)
    return [list(result.hypotheses[0]) for result in results]


class SentencePieceEngine:
    def __init__(self, model_dir: Path, source: str, target: str) -> None:
        import sentencepiece

        self._translator = _translator(model_dir)
        self._pieces = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / SENTENCEPIECE_FILE))
        self._source = source
        self._target = target

    def translate(self, sentences: Sequence[str]) -> str:
        batch = [self._pieces.encode(prepare(sentence, self._source), out_type=str) for sentence in sentences]
        translated = [join_pieces(self._pieces.decode(tokens)) for tokens in _best(self._translator, batch)]
        return join_sentences(list(map(restore, sentences, translated)), self._target)


class MosesBpeEngine:
    def __init__(self, model_dir: Path, source: str, target: str) -> None:
        from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
        from subword_nmt.apply_bpe import BPE

        self._translator = _translator(model_dir)
        self._source = source
        self._target = target
        self._normalizer = MosesPunctNormalizer(source)
        self._tokenizer = MosesTokenizer(source)
        self._detokenizer = MosesDetokenizer(target)
        with (model_dir / BPE_FILE).open(encoding="utf-8") as codes:
            self._bpe = BPE(codes)

    def translate(self, sentences: Sequence[str]) -> str:
        batch = [self._encode(prepare(sentence, self._source)) for sentence in sentences]
        translated = [self._decode(tokens) for tokens in _best(self._translator, batch)]
        return join_sentences(list(map(restore, sentences, translated)), self._target)

    def _encode(self, sentence: str) -> list[str]:
        words = self._tokenizer.tokenize(self._normalizer.normalize(sentence))
        return list(self._bpe.segment_tokens(words))

    def _decode(self, tokens: list[str]) -> str:
        return str(self._detokenizer.detokenize(" ".join(tokens).replace("@@ ", "").split(" ")))
