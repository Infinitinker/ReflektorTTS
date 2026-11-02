"""How kept glossary terms are put back into a translation, for each output language.

A kept term reaches the model as a stand-in name, which the model declines and fits the words
around to. Putting the term back in its place is grammar of the output language: the ending, and
words such as prepositions that depend on how the term begins.
"""

from typing import Protocol

from reflektortts.glossary import GlossaryTerm
from reflektortts.stages.translate.languages.polish import Polish


class OutputLanguage(Protocol):
    def tidy(self, translated: str) -> str:
        """The model's translation with what it gets wrong in this language fixed."""

    def declined(self, term: GlossaryTerm, ending: str) -> str:
        """The term with the ending the model gave its stand-in."""

    def before(self, word: str, term: GlossaryTerm) -> str:
        """The word before a stand-in, fitted to the term put in its place, keeping its case."""


class Undeclined:
    """A language without rules: a kept term is put back as written."""

    def tidy(self, translated: str) -> str:
        return translated

    def declined(self, term: GlossaryTerm, ending: str) -> str:
        return term.term

    def before(self, word: str, term: GlossaryTerm) -> str:
        return word


OUTPUT_LANGUAGES: dict[str, OutputLanguage] = {"pl": Polish()}


def output_language(code: str) -> OutputLanguage:
    return OUTPUT_LANGUAGES.get(code, Undeclined())
