"""Output languages: the language lines should end up in, chosen by the user."""

DEFAULT_LANGUAGE = "en"


class LanguageError(Exception):
    """An output language is not supported; the message lists the supported ones."""


# ISO 639-1 code mapped to the language's own name, as shown to users.
LANGUAGES = {
    "en": "English",
    "pl": "Polski",
}
