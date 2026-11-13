"""Polish after translation: name endings joined back, kept names declined, and "z" and "w" fitted to them."""

import pytest

from reflektortts.glossary import GlossaryTerm
from reflektortts.stages.translate.languages.polish import Polish

POLISH = Polish()


@pytest.mark.parametrize(
    ("translated", "tidied"),
    [
        ("Zabij Frenzy 'ego!", "Zabij Frenzy'ego!"),
        ("Daj to Joe 'mu.", "Daj to Joe'mu."),
        ("Powiedział 'tak' i wyszedł.", "Powiedział 'tak' i wyszedł."),
        ("Misja zakończona!", "Misja zakończona!"),
    ],
)
def test_name_endings_the_model_set_apart_are_joined_to_the_name(translated: str, tidied: str) -> None:
    assert POLISH.tidy(translated) == tidied


@pytest.mark.parametrize(
    ("term", "ending", "declined"),
    [
        (GlossaryTerm("Sweet", keep=True), "owi", "Sweetowi"),
        (GlossaryTerm("Big Smoke", keep=True), "a", "Big Smoke'a"),
        (GlossaryTerm("Kendl", keep=True, female=True), "ą", "Kendl"),
        (GlossaryTerm("Truth", keep=True), "", "Truth"),
        (GlossaryTerm("Big Smoke", keep=True), "em", "Big Smoke'iem"),
        (GlossaryTerm("Greg", keep=True), "em", "Gregiem"),
        (GlossaryTerm("Big Smoke", keep=True, pronounce={"pl": "Big Smołk"}), "ie", "Big Smoke'u"),
        (GlossaryTerm("Greg", keep=True), "owi", "Gregowi"),
    ],
)
def test_a_kept_name_takes_the_stand_ins_ending(term: GlossaryTerm, ending: str, declined: str) -> None:
    assert POLISH.declined(term, ending) == declined


@pytest.mark.parametrize(
    ("word", "term", "fitted"),
    [
        ("z", GlossaryTerm("Sweet", keep=True), "ze"),
        ("ze", GlossaryTerm("Carl", keep=True), "z"),
        ("z", GlossaryTerm("Sabina", keep=True), "z"),
        ("z", GlossaryTerm("Shane", keep=True), "z"),
        ("z", GlossaryTerm("Szkot", keep=True), "ze"),
        ("Z", GlossaryTerm("Sweet", keep=True), "Ze"),
        ("z", GlossaryTerm("Cesar", keep=True, pronounce={"pl": "Sesar"}), "z"),
        ("z", GlossaryTerm("Psycho", keep=True, pronounce={"pl": "Sajko"}), "z"),
        ("z", GlossaryTerm("Stan", keep=True, pronounce={"pl": "Sten"}), "ze"),
        ("w", GlossaryTerm("Wrocław", keep=True), "we"),
        ("we", GlossaryTerm("Vinewood", keep=True), "w"),
        ("w", GlossaryTerm("Fresno", keep=True), "we"),
        ("i", GlossaryTerm("Sweet", keep=True), "i"),
    ],
)
def test_z_and_w_take_their_long_form_before_a_cluster(word: str, term: GlossaryTerm, fitted: str) -> None:
    assert POLISH.before(word, term) == fitted
