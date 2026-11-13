"""How the desktop app tells the user that something failed."""

from reflektortts.desktop.application import error_text


def test_an_error_puts_the_core_s_message_on_a_line_of_its_own() -> None:
    message = "Close VLC first, then try again: VLC writes back its own settings when it closes."

    text = error_text("The VLC integration could not be enabled", message)

    assert text == f"The VLC integration could not be enabled.\n{message}"
