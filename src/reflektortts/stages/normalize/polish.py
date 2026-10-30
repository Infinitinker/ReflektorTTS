"""How Polish says numbers, money and percentages."""

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


def cardinal(value: int) -> str:
    return str(num2words(value, lang="pl"))


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
