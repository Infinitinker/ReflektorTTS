"""How Polish says numbers, money and percentages."""

import re

from num2words import num2words

from reflektortts.stages.normalize.text import Number

# Polish nouns after a number take one of three forms: 1 dolar, 2-4 dolary, 5+ dolarów.
Forms = tuple[str, str, str]

# Main unit and minor unit forms; None where there is no minor unit.
CURRENCIES: dict[str, tuple[Forms, Forms | None]] = {
    "USD": (("dolar", "dolary", "dolarów"), ("cent", "centy", "centów")),
    "EUR": (("euro", "euro", "euro"), ("cent", "centy", "centów")),
    "GBP": (("funt", "funty", "funtów"), ("pens", "pensy", "pensów")),
    "JPY": (("jen", "jeny", "jenów"), None),
    "PLN": (("złoty", "złote", "złotych"), ("grosz", "grosze", "groszy")),
}


# Only 1 and 2, alone or ending a number ("dwadzieścia dwa"), change with the noun's gender:
# jeden/jedna/jedno, dwa/dwie/dwa, and "jedną" before a feminine noun in the accusative
# ("jedną minutę"). num2words writes the masculine forms; nouns common in games switch them.
# Each noun is listed as it follows the number: singular after 1, plural after 2.
FEMININE_NOUNS = (
    *(("minuta", "minuty"), ("sekunda", "sekundy"), ("godzina", "godziny"), ("doba", "doby"), ("noc", "noce")),
    *(("runda", "rundy"), ("misja", "misje"), ("szansa", "szanse"), ("próba", "próby"), ("gra", "gry")),
    *(("osoba", "osoby"), ("kobieta", "kobiety"), ("dziewczyna", "dziewczyny"), ("ofiara", "ofiary")),
    *(("drużyna", "drużyny"), ("gwiazdka", "gwiazdki"), ("gwiazda", "gwiazdy"), ("część", "części")),
    *(("rzecz", "rzeczy"), ("sprawa", "sprawy"), ("wiadomość", "wiadomości"), ("sztuka", "sztuki")),
    *(("rakieta", "rakiety"), ("bomba", "bomby"), ("mina", "miny"), ("kula", "kule"), ("beczka", "beczki")),
    *(("skrzynia", "skrzynie"), ("paczka", "paczki"), ("walizka", "walizki"), ("butelka", "butelki")),
    *(("apteczka", "apteczki"), ("karta", "karty"), ("kamera", "kamery"), ("budka", "budki"), ("łódź", "łodzie")),
    *(("ciężarówka", "ciężarówki"), ("taksówka", "taksówki"), ("furgonetka", "furgonetki")),
    *(("limuzyna", "limuzyny"), ("ulica", "ulice"), ("przecznica", "przecznice"), ("dzielnica", "dzielnice")),
    *(("mila", "mile"), ("stopa", "stopy"), ("tona", "tony"), ("złotówka", "złotówki")),
)
NEUTER_NOUNS = (
    *(("auto", "auta"), ("życie", "życia"), ("zadanie", "zadania"), ("miejsce", "miejsca"), ("piętro", "piętra")),
    *(("okno", "okna"), ("koło", "koła"), ("ciało", "ciała"), ("zabójstwo", "zabójstwa"), ("euro", "euro")),
)
# Nouns in -a end in -ę in the accusative singular: "minuta" becomes "minutę".
FEMININE_ACCUSATIVE = frozenset(singular[:-1] + "ę" for singular, _ in FEMININE_NOUNS if singular.endswith("a"))
FEMININE = frozenset(form for forms in FEMININE_NOUNS for form in forms)
NEUTER = frozenset(form for forms in NEUTER_NOUNS for form in forms)
_ONE_OR_TWO = re.compile(r"\b(jeden|dwa)\b(?=\s+(\w+))", re.IGNORECASE)


def cardinal(value: int) -> str:
    return str(num2words(value, lang="pl"))


def _agreeing(match: re.Match[str]) -> str:
    number, noun = match[1].lower(), match[2].lower()
    if number == "jeden" and noun in FEMININE_ACCUSATIVE:
        word = "jedną"
    elif noun in FEMININE:
        word = "jedna" if number == "jeden" else "dwie"
    elif noun in NEUTER:
        word = "jedno" if number == "jeden" else "dwa"
    else:
        return match[1]
    return word.capitalize() if match[1][0].isupper() else word


def form(value: int, forms: Forms) -> str:
    if value == 1:
        return forms[0]
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return forms[1]
    return forms[2]


def fraction_words(fraction: str) -> str:
    """Polish reads decimals as a number, after any leading zeros: "1,05" is "jeden przecinek zero pięć"."""
    zeros = len(fraction) - len(fraction.lstrip("0"))
    rest = fraction.lstrip("0")
    return " ".join([cardinal(0)] * zeros + ([cardinal(int(rest))] if rest else []))


class PolishWords:
    def number(self, number: Number) -> str:
        if number.is_code:
            return " ".join(cardinal(int(digit)) for digit in number.written)
        words = cardinal(number.whole)
        if number.fraction:
            words += f" przecinek {fraction_words(number.fraction)}"
        return words

    def money(self, currency: str, number: Number) -> str:
        main, minor = CURRENCIES[currency]
        words = f"{cardinal(number.whole)} {form(number.whole, main)}"
        if minor is not None and number.cents:
            words += f" {cardinal(number.cents)} {form(number.cents, minor)}"
        return words

    def percent(self, number: Number) -> str:
        return f"{self.number(number)} procent"

    def agree(self, text: str) -> str:
        """Gives 1 and 2 the gender of the noun after them: "dwa minuty" becomes "dwie minuty"."""
        return _ONE_OR_TWO.sub(_agreeing, text)
