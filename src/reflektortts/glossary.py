"""A profile's glossary: words and phrases of its app that translation and speech treat specially."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    """As the app writes it, e.g. "Big Smoke"."""
    keep: bool = False
    """Never translated, e.g. a name that is also a word ("Sweet")."""
    female: bool = False
    """A kept term is a woman's name, so translation declines it as one."""
    means: str | None = None
    """Plain words in the input language the term is translated as, e.g. "neighborhood" for "hood"."""
    say: Mapping[str, str] = field(default_factory=dict)
    """How the term is spoken, by output language (ISO 639-1), e.g. {"pl": "Karl"} for "Carl"."""


type Glossary = tuple[GlossaryTerm, ...]
