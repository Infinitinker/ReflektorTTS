import pytest

from reflektortts.glossary import GlossaryTerm
from reflektortts.stages.translate.glossary import GlossaryRules
from reflektortts.stages.translate.languages import output_language

RULES = GlossaryRules(
    (
        GlossaryTerm("Sweet", keep=True),
        GlossaryTerm("Big Smoke", keep=True),
        GlossaryTerm("Kendl", keep=True, female=True),
        GlossaryTerm("OG", keep=True),
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
        ("Some Grove Street OG started it.", "Some Grove Street Kevin started it."),
        ("Lindsay saw Kendl.", "Lindsay saw Laura."),
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
        ("Stay with Sweet.", "Zostań z Kevinem.", "Zostań ze Sweetem."),
        ("With Sweet, always.", "Z Kevinem, zawsze.", "Ze Sweetem, zawsze."),
        ("STAY WITH SWEET!", "ZOSTAŃ Z KEVINEM!", "ZOSTAŃ ZE SWEETEM!"),
        (
            "Kevin and Brian came with Big Smoke.",
            "Kevin i Brian przyszli ze Stevenem.",
            "Kevin i Brian przyszli z Big Smoke'iem.",
        ),
    ],
)
def test_stand_ins_are_put_back_with_their_polish_endings(line: str, translated: str, put_back: str) -> None:
    assert RULES.prepare(line).put_back(translated, output_language("pl")) == put_back


def test_in_a_language_without_rules_a_kept_term_is_put_back_as_written() -> None:
    prepared = RULES.prepare("Tell Sweet I'm coming.")

    assert prepared.put_back("Sag Kevins Freund, dass ich komme.", output_language("de")) == (
        "Sag Sweet Freund, dass ich komme."
    )


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
    assert prepared.put_back("Powiedz Sweetowi.", output_language("pl")) == "Powiedz Sweetowi."


def test_a_line_can_hold_ten_kept_names() -> None:
    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliett"]
    rules = GlossaryRules(tuple(GlossaryTerm(name, keep=True) for name in names))
    line = ", ".join(names) + "."

    prepared = rules.prepare(line)

    assert not any(name in prepared.text for name in names)
    assert prepared.put_back(prepared.text, output_language("pl")) == line
