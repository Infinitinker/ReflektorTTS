"""Finding a glossary's terms in text: in each spelling, in capitals, and as whole words only."""

from reflektortts.glossary import GlossaryTerm, TermFinder

SMOKE = GlossaryTerm("Big Smoke", keep=True, other_spellings=("Big smoke",))
CJ = GlossaryTerm("CJ", pronounce={"pl": "Sidżej"})
FINDER = TermFinder((SMOKE, CJ))


def test_a_term_is_found_in_each_spelling_and_put_as_the_text_spells_it() -> None:
    assert FINDER.found("Big Smoke") == (SMOKE, False)
    assert FINDER.found("Big smoke") == (GlossaryTerm("Big smoke", keep=True, other_spellings=("Big Smoke",)), False)


def test_a_term_in_capitals_is_shouted_unless_the_glossary_writes_it_so() -> None:
    assert FINDER.found("BIG SMOKE") == (SMOKE, True)
    assert FINDER.found("CJ") == (CJ, False)


def test_terms_are_found_as_whole_words_only() -> None:
    pattern = FINDER.whole_words()

    assert pattern is not None
    assert pattern.findall("Big smoke and CJ, not a big smoke or CJs.") == ["Big smoke", "CJ"]
    assert TermFinder(()).whole_words() is None
