"""Splits lines into sentences: translation models are trained on single sentences and drop
the rest of longer input."""

import re

# A sentence ends at . ! ? … (or Arabic ؟, Urdu ۔, Hindi । ॥, Armenian ։, Ethiopic ።, Burmese ။,
# Tibetan །, Khmer ។), optionally followed by closing quotes or brackets (French puts a space
# before its closing »), then whitespace or the end; or at the full stops of Chinese and Japanese
# (also doubled, as in ！？), which have no space after them. A straight quote there may close the
# sentence or open the next one, so it goes to the one whose quotes it balances.
_SENTENCE = re.compile(
    r"\S.*?(?:[.!?…؟۔।॥։።။།។](?:[\"'”’“‘»«)\]]|[ \u00a0\u202f]»)*(?=\s|$)"
    r"|[。！？]+[」』）〕】”’]*|$)",
    re.DOTALL,
)


def split_sentences(text: str) -> list[str]:
    sentences = [match.group().strip() for match in _SENTENCE.finditer(text.strip())]
    for index in range(len(sentences) - 1):
        if sentences[index].count('"') % 2 and sentences[index + 1].startswith('"'):
            sentences[index] += '"'
            sentences[index + 1] = sentences[index + 1][1:].lstrip()
    return [sentence for sentence in sentences if sentence]
