"""How English says numbers, money, percentages, units, dates, times and abbreviations."""

from num2words import num2words

from reflektortts.stages.normalize.text import Number, expand_words

# Main unit (one, many) and minor unit (one, many); None where there is no minor unit.
CURRENCIES: dict[str, tuple[tuple[str, str], tuple[str, str] | None]] = {
    "USD": (("dollar", "dollars"), ("cent", "cents")),
    "EUR": (("euro", "euros"), ("cent", "cents")),
    "GBP": (("pound", "pounds"), ("penny", "pence")),
    "JPY": (("yen", "yen"), None),
    "PLN": (("zloty", "zlotys"), ("grosz", "groszy")),
}

UNITS: dict[str, tuple[str, str]] = {
    "km": ("kilometer", "kilometers"),
    "m": ("meter", "meters"),
    "cm": ("centimeter", "centimeters"),
    "mm": ("millimeter", "millimeters"),
    "kg": ("kilogram", "kilograms"),
    "g": ("gram", "grams"),
    "l": ("liter", "liters"),
    "ml": ("milliliter", "milliliters"),
    "h": ("hour", "hours"),
    "min": ("minute", "minutes"),
    "s": ("second", "seconds"),
    "°C": ("degree Celsius", "degrees Celsius"),
    "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
}

ABBREVIATIONS = {
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Dr.": "Doctor",
    "vs.": "versus",
    "etc.": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
}
SYMBOLS = {"&": "and", "+": "plus"}

MONTHS = (
    *("January", "February", "March", "April", "May", "June"),
    *("July", "August", "September", "October", "November", "December"),
)


def cardinal(value: int) -> str:
    # num2words writes "one thousand, five hundred"; the comma would make voices pause.
    return str(num2words(value, lang="en")).replace(",", "")


def digits(text: str) -> str:
    return " ".join(cardinal(int(digit)) for digit in text)


def form(value: int, forms: tuple[str, str]) -> str:
    return forms[0] if value == 1 else forms[1]


class EnglishWords:
    def expand(self, text: str) -> str:
        return expand_words(text, ABBREVIATIONS, SYMBOLS)

    def date(self, day: int, month: int, year: int) -> str:
        ordinal = num2words(day, lang="en", to="ordinal")
        return f"the {ordinal} of {MONTHS[month - 1]} {num2words(year, lang='en', to='year')}"

    def time(self, hour: int, minute: int) -> str:
        """24-hour times as said aloud: "fourteen thirty", "nine oh five", "ten o'clock"."""
        if minute == 0:
            return f"{cardinal(hour)} o'clock" if hour <= 12 else f"{cardinal(hour)} hundred"
        return f"{cardinal(hour)} {'oh ' if minute < 10 else ''}{cardinal(minute)}"

    def unit(self, unit: str, number: Number) -> str:
        one, many = UNITS[unit]
        return f"{self.number(number)} {one if number.whole == 1 and not number.fraction else many}"

    def number(self, number: Number) -> str:
        if number.is_code:
            return digits(number.written)
        words = cardinal(number.whole)
        if number.fraction:
            words += f" point {digits(number.fraction)}"
        return words

    def money(self, currency: str, number: Number) -> str:
        main, minor = CURRENCIES[currency]
        words = f"{cardinal(number.whole)} {form(number.whole, main)}"
        if minor is not None and number.cents:
            words += f" and {cardinal(number.cents)} {form(number.cents, minor)}"
        return words

    def percent(self, number: Number) -> str:
        return f"{self.number(number)} percent"

    def agree(self, text: str) -> str:
        """English numbers do not change with the words after them."""
        return text
