import pytest

from reflektortts.events import TextEvent
from reflektortts.languages import LANGUAGES
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.normalize.stage import PLUGIN, WORDS


def say(text: str, language: str) -> str:
    event = PLUGIN.create({}).process(TextEvent("messages", text, 0.0, language))
    assert event is not None
    return event.text


@pytest.mark.parametrize(
    ("text", "english", "polish"),
    [
        ("$50,000", "fifty thousand dollars", "pięćdziesiąt tysięcy dolarów"),
        ("$1", "one dollar", "jeden dolar"),
        ("$22", "twenty-two dollars", "dwadzieścia dwa dolary"),
        ("$12.50", "twelve dollars and fifty cents", "dwanaście dolarów pięćdziesiąt centów"),
        ("€5", "five euros", "pięć euro"),
        ("£3", "three pounds", "trzy funty"),
        ("10 zł", "ten zlotys", "dziesięć złotych"),
        (
            "1 500,99 zł",
            "one thousand five hundred zlotys and ninety-nine groszy",
            "tysiąc pięćset złotych dziewięćdziesiąt dziewięć groszy",
        ),
        ("50%", "fifty percent", "pięćdziesiąt procent"),
        ("2.5", "two point five", "dwa przecinek pięć"),
        ("1,05", "one point zero five", "jeden przecinek zero pięć"),
        ("1,000,000", "one million", "milion"),
        ("5551234", "five five five one two three four", "pięć pięć pięć jeden dwa trzy cztery"),
    ],
)
def test_numbers_money_and_percentages_are_spelled_out(text: str, english: str, polish: str) -> None:
    assert say(text, "en") == english
    assert say(text, "pl") == polish


def test_a_gta2_line_reads_naturally() -> None:
    line = "Take the car to the docks for $50,000, then come back."

    assert say(line, "en") == "Take the car to the docks for fifty thousand dollars, then come back."


def test_text_without_numbers_and_empty_text_pass_unchanged() -> None:
    assert say("Kill Frenzy!", "en") == "Kill Frenzy!"
    assert say("", "pl") == ""


def test_a_language_without_rules_passes_lines_unchanged() -> None:
    assert say("$5", "xx") == "$5"


def test_every_output_language_has_rules() -> None:
    assert set(WORDS) == set(LANGUAGES)


def test_plugin_is_registered() -> None:
    assert stage_plugins()["normalize"] is PLUGIN
