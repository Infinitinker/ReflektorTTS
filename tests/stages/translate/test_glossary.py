import pytest

from reflektortts.glossary import GlossaryTerm
from reflektortts.stages.translate.glossary import GlossaryRules

RULES = GlossaryRules(
    (
        GlossaryTerm("Sweet", keep=True),
        GlossaryTerm("Big Smoke", keep=True),
        GlossaryTerm("Kendl", keep=True, female=True),
        GlossaryTerm("hood", means="neighborhood"),
        GlossaryTerm("Carl", pronounce={"pl": "Karl"}),
        GlossaryTerm("Zero", pronounce={"pl": "Zirou"}),
    )
)


@pytest.mark.parametrize(
    ("line", "for_the_model"),
    [
        ("Tell Sweet I'm coming.", "Tell Kevin I'm coming."),
        ("Sweet and Big Smoke are here.", "Kevin and Brian are here."),
        ("Sweet, sweet Sweet.", "Kevin, sweet Kevin."),
        ("Go get Kendl!", "Go get Linda!"),
        ("GET IN, SWEET!", "GET IN, KEVIN!"),
        ("Kevin knows Sweet.", "Kevin knows Brian."),
        ("Back to the hood. Hood rules! HOOD!", "Back to the neighborhood. Neighborhood rules! NEIGHBORHOOD!"),
        ("Hoodie and childhood stay.", "Hoodie and childhood stay."),
    ],
)
def test_kept_terms_get_stand_ins_and_terms_with_a_meaning_are_rewritten(line: str, for_the_model: str) -> None:
    assert RULES.prepare(line).text == for_the_model


@pytest.mark.parametrize(
    ("line", "translated", "put_back"),
    [
        ("Tell Sweet I'm coming.", "Powiedz Kevinowi, że idę.", "Powiedz Sweetowi, że idę."),
        ("Where is Big Smoke's car?", "Gdzie jest samochód Kevina?", "Gdzie jest samochód Big Smoke'a?"),
        ("I was with Kendl.", "Byłem z Lindą.", "Byłem z Kendl."),
        ("Go get Kendl!", "Idź po Lindę!", "Idź po Kendl!"),
        ("GET IN, SWEET!", "WSIADAJ, KEVIN!", "WSIADAJ, SWEET!"),
        ("Sweet and Big Smoke are here.", "Kevin i Brian tu są.", "Sweet i Big Smoke tu są."),
    ],
)
def test_stand_ins_are_put_back_with_their_polish_endings(line: str, translated: str, put_back: str) -> None:
    assert RULES.prepare(line).put_back(translated) == put_back


@pytest.mark.parametrize(
    ("line", "letters"),
    [
        ("Carl, Zero, Zero, Carl.", 0),
        ("CARL!", 0),
        ("Sweet!", 0),
        ("Hood!", 4),
        ("Smash, Carl, smash!", 10),
        ("Carlos?", 6),
    ],
)
def test_the_skip_count_sets_aside_kept_and_pronounced_terms(line: str, letters: int) -> None:
    assert RULES.letters_besides_terms(line) == letters


def test_without_a_glossary_lines_pass_unchanged() -> None:
    prepared = GlossaryRules(()).prepare("Tell Sweet I'm coming.")

    assert prepared.text == "Tell Sweet I'm coming."
    assert prepared.put_back("Powiedz Sweetowi.") == "Powiedz Sweetowi."
