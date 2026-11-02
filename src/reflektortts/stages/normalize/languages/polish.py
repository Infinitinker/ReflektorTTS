"""How Polish says numbers, money, percentages, units, dates, times and abbreviations."""

import re

from num2words import num2words

from reflektortts.stages.normalize.text import Number, expand_words

# Polish nouns after a number take one of three forms: 1 dolar, 2-4 dolary, 5+ dolarów.
Forms = tuple[str, str, str]

# Units also take a fourth form after a decimal: "1,5 kilometra".
UNITS: dict[str, tuple[str, str, str, str]] = {
    "km": ("kilometr", "kilometry", "kilometrów", "kilometra"),
    "m": ("metr", "metry", "metrów", "metra"),
    "cm": ("centymetr", "centymetry", "centymetrów", "centymetra"),
    "mm": ("milimetr", "milimetry", "milimetrów", "milimetra"),
    "kg": ("kilogram", "kilogramy", "kilogramów", "kilograma"),
    "g": ("gram", "gramy", "gramów", "grama"),
    "l": ("litr", "litry", "litrów", "litra"),
    "ml": ("mililitr", "mililitry", "mililitrów", "mililitra"),
    "h": ("godzina", "godziny", "godzin", "godziny"),
    "min": ("minuta", "minuty", "minut", "minuty"),
    "s": ("sekunda", "sekundy", "sekund", "sekundy"),
    "°C": ("stopień Celsjusza", "stopnie Celsjusza", "stopni Celsjusza", "stopnia Celsjusza"),
    "°F": ("stopień Fahrenheita", "stopnie Fahrenheita", "stopni Fahrenheita", "stopnia Fahrenheita"),
}

ABBREVIATIONS = {
    "nr": "numer",
    "ul.": "ulica",
    "al.": "aleja",
    "pl.": "plac",
    "tel.": "telefon",
    "godz.": "godzina",
    "np.": "na przykład",
    "m.in.": "między innymi",
    "tzn.": "to znaczy",
    "tzw.": "tak zwany",
    "dr": "doktor",
    "mgr": "magister",
}
SYMBOLS = {"&": "i", "+": "plus"}

MONTHS = (
    *("stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca"),
    *("lipca", "sierpnia", "września", "października", "listopada", "grudnia"),
)
# Ordinals in the genitive, as dates are said: "dwunastego maja".
ORDINAL_UNITS = (
    *("", "pierwszego", "drugiego", "trzeciego", "czwartego"),
    *("piątego", "szóstego", "siódmego", "ósmego", "dziewiątego"),
)
ORDINAL_TEENS = (
    *("dziesiątego", "jedenastego", "dwunastego", "trzynastego", "czternastego"),
    *("piętnastego", "szesnastego", "siedemnastego", "osiemnastego", "dziewiętnastego"),
)
ORDINAL_TENS = (
    *("", "", "dwudziestego", "trzydziestego", "czterdziestego"),
    *("pięćdziesiątego", "sześćdziesiątego", "siedemdziesiątego", "osiemdziesiątego", "dziewięćdziesiątego"),
)
# Hours are feminine ordinals: "czternasta trzydzieści".
HOURS = (
    *("zero", "pierwsza", "druga", "trzecia", "czwarta", "piąta", "szósta", "siódma", "ósma", "dziewiąta"),
    *("dziesiąta", "jedenasta", "dwunasta", "trzynasta", "czternasta", "piętnasta", "szesnasta"),
    *("siedemnasta", "osiemnasta", "dziewiętnasta", "dwudziesta", "dwudziesta pierwsza"),
    *("dwudziesta druga", "dwudziesta trzecia"),
)

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

# After these prepositions an hour (and "godzina") changes case: "o czternastej", "przed
# czternastą". Each maps to the ending of the hour's words and the form of "godzina".
HOUR_CASES = {
    "o": ("ej", "godzinie"),
    "po": ("ej", "godzinie"),
    "do": ("ej", "godziny"),
    "od": ("ej", "godziny"),
    "około": ("ej", "godziny"),
    "przed": ("ą", "godziną"),
}
_HOUR_WORDS = "|".join(sorted((hour for hour in HOURS if hour.endswith("a")), key=len, reverse=True))
_HOUR_AFTER_PREPOSITION = re.compile(
    rf"\b(?P<preposition>{'|'.join(HOUR_CASES)})\s+(?P<noun>godzina\s+)?(?P<hour>{_HOUR_WORDS})\b", re.IGNORECASE
)


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


def _hour_in_case(match: re.Match[str]) -> str:
    ending, noun = HOUR_CASES[match["preposition"].lower()]
    hour = " ".join(word[:-1] + ending for word in match["hour"].split())
    return f"{match['preposition']} {noun + ' ' if match['noun'] else ''}{hour}"


def form(value: int, forms: Forms) -> str:
    if value == 1:
        return forms[0]
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return forms[1]
    return forms[2]


def ordinal_genitive(value: int) -> str:
    """1 to 99: "dwunastego", "dwudziestego pierwszego"."""
    if value < 10:
        return ORDINAL_UNITS[value]
    if value < 20:
        return ORDINAL_TEENS[value - 10]
    tens, units = divmod(value, 10)
    return ORDINAL_TENS[tens] + (f" {ORDINAL_UNITS[units]}" if units else "")


def year_genitive(year: int) -> str:
    """Years are ordinals too: "dwa tysiące dwudziestego czwartego"; others read as numbers."""
    if year == 2000:
        return "dwutysięcznego"
    if 2001 <= year <= 2099:
        return f"dwa tysiące {ordinal_genitive(year - 2000)}"
    if year == 1900:
        return "tysiąc dziewięćsetnego"
    if 1901 <= year <= 1999:
        return f"tysiąc dziewięćset {ordinal_genitive(year - 1900)}"
    return cardinal(year)


def fraction_words(fraction: str) -> str:
    """Polish reads decimals as a number, after any leading zeros: "1,05" is "jeden przecinek zero pięć"."""
    zeros = len(fraction) - len(fraction.lstrip("0"))
    rest = fraction.lstrip("0")
    return " ".join([cardinal(0)] * zeros + ([cardinal(int(rest))] if rest else []))


class PolishWords:
    def expand(self, text: str) -> str:
        return expand_words(text, ABBREVIATIONS, SYMBOLS)

    def date(self, day: int, month: int, year: int) -> str:
        return f"{ordinal_genitive(day)} {MONTHS[month - 1]} {year_genitive(year)}"

    def time(self, hour: int, minute: int) -> str:
        if minute == 0:
            return HOURS[hour]
        return f"{HOURS[hour]} {'zero ' if minute < 10 else ''}{cardinal(minute)}"

    def unit(self, unit: str, number: Number) -> str:
        one, few, many, of_fraction = UNITS[unit]
        noun = of_fraction if number.fraction else form(number.whole, (one, few, many))
        return f"{self.number(number)} {noun}"

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
        """Gives 1 and 2 the gender of the noun after them ("dwa minuty" becomes "dwie minuty"),
        and hours the case their preposition needs ("o czternasta" becomes "o czternastej")."""
        return _HOUR_AFTER_PREPOSITION.sub(_hour_in_case, _ONE_OR_TWO.sub(_agreeing, text))
