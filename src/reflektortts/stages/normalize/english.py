"""How English says numbers, money and percentages."""

from num2words import num2words

from reflektortts.stages.normalize.text import Number

# Main unit (one, many) and minor unit (one, many); None where there is no minor unit.
CURRENCIES: dict[str, tuple[tuple[str, str], tuple[str, str] | None]] = {
    "USD": (("dollar", "dollars"), ("cent", "cents")),
    "EUR": (("euro", "euros"), ("cent", "cents")),
    "GBP": (("pound", "pounds"), ("penny", "pence")),
    "JPY": (("yen", "yen"), None),
    "PLN": (("zloty", "zlotys"), ("grosz", "groszy")),
}


def cardinal(value: int) -> str:
    # num2words writes "one thousand, five hundred"; the comma would make voices pause.
    return str(num2words(value, lang="en")).replace(",", "")


def digits(text: str) -> str:
    return " ".join(cardinal(int(digit)) for digit in text)


def form(value: int, forms: tuple[str, str]) -> str:
    return forms[0] if value == 1 else forms[1]


class EnglishWords:
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
