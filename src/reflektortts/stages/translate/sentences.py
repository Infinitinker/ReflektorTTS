"""Splits lines into sentences: translation models are trained on single sentences and drop
the rest of longer input."""

import re

# A sentence ends at . ! ? or …, optionally followed by a closing quote or bracket, then whitespace.
_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\"'”’)\]])\s+")


def split_sentences(text: str) -> list[str]:
    return [sentence for sentence in _BOUNDARY.split(text.strip()) if sentence]
