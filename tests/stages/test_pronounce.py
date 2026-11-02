import pytest

from reflektortts.events import TextEvent
from reflektortts.glossary import GlossaryTerm
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.pronounce import PLUGIN

GLOSSARY = (
    GlossaryTerm("Carl", pronounce={"pl": "Karl"}),
    GlossaryTerm("Big Smoke", keep=True, pronounce={"pl": "Big Smołk"}),
    GlossaryTerm("Sweet", keep=True),
)


def pronounced(text: str, language: str = "pl") -> str:
    event = PLUGIN.create({}, GLOSSARY).process(TextEvent("subtitles", text, 0.0, output_language=language))
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
    ],
)
def test_terms_are_respelled_for_the_output_language_with_their_endings(text: str, spoken: str) -> None:
    assert pronounced(text) == spoken


def test_a_language_without_pronunciations_is_left_as_is() -> None:
    assert pronounced("Hey, Carl. Carla?", "en") == "Hey, Carl. Carla?"


def test_the_plugin_is_registered() -> None:
    assert stage_plugins()["pronounce"] is PLUGIN
