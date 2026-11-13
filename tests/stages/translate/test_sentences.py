"""Splitting lines into sentences for translation."""

import pytest

from reflektortts.stages.translate.sentences import split_sentences


@pytest.mark.parametrize(
    ("text", "sentences"),
    [
        ("Kill Frenzy!", ["Kill Frenzy!"]),
        (
            "Where have you been? I've been looking for you all day.",
            ["Where have you been?", "I've been looking for you all day."],
        ),
        (
            "Hey there, stranger! Welcome to the Downtown District. Stick around...",
            ["Hey there, stranger!", "Welcome to the Downtown District.", "Stick around..."],
        ),
        ('He said "Go!" Then he left.', ['He said "Go!"', "Then he left."]),
        ("Wait… What?", ["Wait…", "What?"]),
        ("  Bring me $50,000 and we'll talk.  ", ["Bring me $50,000 and we'll talk."]),
        ("", []),
        ("こんにちは。元気ですか？はい", ["こんにちは。", "元気ですか？", "はい"]),
        ("本当！？嘘でしょ", ["本当！？", "嘘でしょ"]),
        ('他走了。"你好吗？"', ["他走了。", '"你好吗？"']),
        ('他说："你好。"然后走了。', ['他说："你好。"', "然后走了。"]),
        ("Բարեւ։ Ինչպես ես?", ["Բարեւ։", "Ինչպես ես?"]),
        ("„Komm her!“ Er ging.", ["„Komm her!“", "Er ging."]),
        ("« Bonjour ! » Il est parti.", ["« Bonjour ! »", "Il est parti."]),
        ("هل أنت بخير؟ نعم.", ["هل أنت بخير؟", "نعم."]),
        ("मैं ठीक हूँ। तुम?", ["मैं ठीक हूँ।", "तुम?"]),
    ],
)
def test_lines_are_split_after_sentence_endings(text: str, sentences: list[str]) -> None:
    assert split_sentences(text) == sentences
