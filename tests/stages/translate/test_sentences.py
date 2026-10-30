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
    ],
)
def test_lines_are_split_after_sentence_endings(text: str, sentences: list[str]) -> None:
    assert split_sentences(text) == sentences
