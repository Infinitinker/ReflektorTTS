"""vlcrc files as VLC 3 writes them, cut down to the lines the VLC integration and source use."""

from reflektortts.sources.vlc.vlcrc import BOM

FRESH = (
    BOM
    + (
        "###\n"
        "###  vlc 3.0.23\n"
        "###\n"
        "\n"
        "###\n"
        "### lines beginning with a '#' character are comments\n"
        "###\n"
        "\n"
        "[http] # HTTP\n"
        "\n"
        "# Hasło serwera pośredniczącego HTTP (ciąg znaków)\n"
        "#http-proxy-pwd=\n"
        "\n"
        "[lua] # Lua interpreter\n"
        "\n"
        "# Hasło (ciąg znaków)\n"
        "#http-password=\n"
        "\n"
        "[http] # HTTP\n"
        "\n"
        "[core] # core program\n"
        "\n"
        "# Interfejs HTTP — host (ciąg znaków)\n"
        "#http-host=\n"
        "\n"
        "# Port HTTP (liczba całkowita)\n"
        "#http-port=8080\n"
        "\n"
        "# Moduły interfejsów dodatkowych (ciąg znaków)\n"
        "#extraintf=\n"
    ).encode()
)
"""A vlcrc with every setting at its default, in a Polish VLC."""


def with_lines(rc: bytes, *lines: str) -> bytes:
    """rc with lines added at its end."""
    return rc + "".join(line + "\n" for line in lines).encode()
