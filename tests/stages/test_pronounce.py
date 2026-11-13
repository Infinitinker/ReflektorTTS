"""The pronounce stage: glossary terms respelled for the output language, keeping their endings."""

import pytest

from reflektortts.events import TextEvent
from reflektortts.glossary import GlossaryTerm
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.pronounce import PLUGIN

GLOSSARY = (
    GlossaryTerm("Carl", pronounce={"pl": "Karl"}),
    GlossaryTerm("Big Smoke", keep=True, pronounce={"pl": "Big Smołk"}, other_spellings=("Big smoke",)),
    GlossaryTerm("Sweet", keep=True),
    GlossaryTerm("CJ", pronounce={"pl": "Si Dżej"}),
)


def pronounced(text: str, language: str = "pl") -> str:
    event = PLUGIN.create({}, {"en": GLOSSARY}).process(TextEvent("subtitles", text, 0.0, output_language=language))
    assert event is not None
    return event.text


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Hej, Carl.", "Hej, Karl."),
        ("Powiedz Carlowi, że idę.", "Powiedz Karlowi, że idę."),
        ("Samochód Carla.", "Samochód Karla."),
        ("Byłem z Big Smoke'iem u Big Smoke'a.", "Byłem z Big Smołkiem u Big Smołka."),
        ("CARL, WSIADAJ!", "KARL, WSIADAJ!"),
        ("SAMOCHÓD CARLA!", "SAMOCHÓD KARLA!"),
        ("Carlos i carl zostają.", "Carlos i carl zostają."),
        ("Sweet żyje.", "Sweet żyje."),
        ("Uważaj, CJ!", "Uważaj, Si Dżej!"),
        ("Big smoke, to ja!", "Big Smołk, to ja!"),
        ("Wielki dym nad big smoke.", "Wielki dym nad big smoke."),
    ],
)
def test_terms_are_respelled_for_the_output_language_with_their_endings(text: str, spoken: str) -> None:
    assert pronounced(text) == spoken


def test_a_line_in_another_input_language_gets_none_of_the_glossary() -> None:
    event = TextEvent("subtitles", "Hej, Carl.", 0.0, output_language="pl", input_language="de")

    processed = PLUGIN.create({}, {"en": GLOSSARY}).process(event)

    assert processed is not None and processed.text == "Hej, Carl."


def test_a_language_without_pronunciations_is_left_as_is() -> None:
    assert pronounced("Hey, Carl. Carla?", "en") == "Hey, Carl. Carla?"


def test_the_plugin_is_registered() -> None:
    assert stage_plugins()["pronounce"] is PLUGIN


def test_terms_are_respelled_in_a_language_without_spaces() -> None:
    glossary = (GlossaryTerm("Carl", pronounce={"zh": "卡尔"}),)
    event = TextEvent("subtitles", "Carl在这里。", 0.0, output_language="zh")

    processed = PLUGIN.create({}, {"en": glossary}).process(event)

    assert processed is not None and processed.text == "卡尔在这里。"


def test_a_longer_latin_name_is_kept_in_a_language_without_spaces() -> None:
    glossary = (GlossaryTerm("Carl", pronounce={"ja": "カール"}),)
    event = TextEvent("subtitles", "Carlosが来た。Carlも。", 0.0, output_language="ja")

    processed = PLUGIN.create({}, {"en": glossary}).process(event)

    assert processed is not None and processed.text == "Carlosが来た。カールも。"
