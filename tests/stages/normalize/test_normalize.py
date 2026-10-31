import pytest

from reflektortts.events import TextEvent
from reflektortts.languages import LANGUAGES, Languages
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.normalize.stage import PLUGIN, WORDS


def say(text: str, language: str) -> str:
    event = PLUGIN.create({}).process(TextEvent("messages", text, 0.0, output_language=language))
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


@pytest.mark.parametrize(
    ("text", "english", "polish"),
    [
        ("14:30", "fourteen thirty", "czternasta trzydzieści"),
        ("9:05", "nine oh five", "dziewiąta zero pięć"),
        ("10:00", "ten o'clock", "dziesiąta"),
        ("18:00", "eighteen hundred", "osiemnasta"),
        ("25:61", "twenty-five: sixty-one", "dwadzieścia pięć: sześćdziesiąt jeden"),
    ],
)
def test_times_of_day_are_said_as_clock_times(text: str, english: str, polish: str) -> None:
    assert say(text, "en") == english
    assert say(text, "pl") == polish


@pytest.mark.parametrize(
    ("text", "english", "polish"),
    [
        ("5 km", "five kilometers", "pięć kilometrów"),
        ("1 km", "one kilometer", "jeden kilometr"),
        ("1.5 km", "one point five kilometers", "jeden przecinek pięć kilometra"),
        ("100 m", "one hundred meters", "sto metrów"),
        ("2 min", "two minutes", "dwie minuty"),
        ("1 h", "one hour", "jedna godzina"),
        ("30 s", "thirty seconds", "trzydzieści sekund"),
        ("20°C", "twenty degrees Celsius", "dwadzieścia stopni Celsjusza"),
        ("3 kg", "three kilograms", "trzy kilogramy"),
    ],
)
def test_units_after_numbers_are_spelled_out(text: str, english: str, polish: str) -> None:
    assert say(text, "en") == english
    assert say(text, "pl") == polish


def test_one_letter_units_need_a_space_so_decades_stay() -> None:
    assert say("Back in the 80s.", "en") == "Back in the eighty s."
    assert say("Run 400m now.", "en") == "Run four hundred m now."


@pytest.mark.parametrize(
    ("text", "english", "polish"),
    [
        ("12.05.2024", "the twelfth of May twenty twenty-four", "dwunastego maja dwa tysiące dwudziestego czwartego"),
        ("2024-05-12", "the twelfth of May twenty twenty-four", "dwunastego maja dwa tysiące dwudziestego czwartego"),
        (
            "1.01.1999",
            "the first of January nineteen ninety-nine",
            "pierwszego stycznia tysiąc dziewięćset dziewięćdziesiątego dziewiątego",
        ),
        ("Up by 1.5.", "Up by one point five.", "Up by jeden przecinek pięć."),
    ],
)
def test_dates_need_a_year_so_decimals_stay_numbers(text: str, english: str, polish: str) -> None:
    assert say(text, "en") == english
    assert say(text, "pl") == polish


@pytest.mark.parametrize(
    ("text", "polish"),
    [
        ("Jedź na ul. Długą, np. teraz.", "Jedź na ulica Długą, na przykład teraz."),
        ("Np. tak.", "Na przykład tak."),
        ("Pokój nr 5, dr Nowak.", "Pokój numer pięć, doktor Nowak."),
        ("OK. Jedziemy, m.in. ty & ja.", "OK. Jedziemy, między innymi ty i ja."),
        ("Bądź o godz. 14:30.", "Bądź o godzinie czternastej trzydzieści."),
        ("Czekaj do 21:05, nie przed 9:00.", "Czekaj do dwudziestej pierwszej zero pięć, nie przed dziewiątą."),
        ("O 1:15 i po 12:00.", "O pierwszej piętnaście i po dwunastej."),
        ("Drzwi, drużyna", "Drzwi, drużyna"),
    ],
)
def test_polish_abbreviations_and_symbols_are_spelled_out(text: str, polish: str) -> None:
    assert say(text, "pl") == polish


def test_english_abbreviations_and_symbols_are_spelled_out() -> None:
    assert say("Ask Dr. Smith, e.g. now. Salt & pepper +1.", "en") == (
        "Ask Doctor Smith, for example now. Salt and pepper plus one."
    )


def test_a_gta2_line_reads_naturally() -> None:
    line = "Take the car to the docks for $50,000, then come back."

    assert say(line, "en") == "Take the car to the docks for fifty thousand dollars, then come back."


@pytest.mark.parametrize(
    ("text", "polish"),
    [
        ("Wyciągnij 20 świrów w 2 minuty.", "Wyciągnij dwadzieścia świrów w dwie minuty."),
        ("Masz 1 minutę? Zostały 2 auta i 1 auto.", "Masz jedną minutę? Zostały dwa auta i jedno auto."),
        ("Zostały 22 sekundy.", "Zostały dwadzieścia dwie sekundy."),
        ("2 misje, 1 noc.", "dwie misje, jedna noc."),
        ("Jeden błąd i Dwa auta.", "Jeden błąd i Dwa auta."),
        ("Masz tylko 1 szansę.", "Masz tylko jedną szansę."),
        ("2 samochody i 21 minut.", "dwa samochody i dwadzieścia jeden minut."),
    ],
)
def test_polish_one_and_two_take_the_gender_of_the_noun_after_them(text: str, polish: str) -> None:
    assert say(text, "pl") == polish


def test_text_without_numbers_and_empty_text_pass_unchanged() -> None:
    assert say("Kill Frenzy!", "en") == "Kill Frenzy!"
    assert say("", "pl") == ""


def test_it_does_nothing_for_an_output_language_without_rules() -> None:
    assert PLUGIN.inactive_reason(Languages(game="en", output="xx")) == "No rules for the output language yet"
    assert PLUGIN.inactive_reason(Languages(game="en", output="pl")) is None


def test_every_output_language_has_rules() -> None:
    assert set(WORDS) == set(LANGUAGES)


def test_plugin_is_registered() -> None:
    assert stage_plugins()["normalize"] is PLUGIN
