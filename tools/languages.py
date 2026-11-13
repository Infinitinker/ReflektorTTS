"""Generates src/reflektortts/languages.json: every ISO 639-1 language, with its own name, its
English name, its ISO 639-2 codes, the code page its text usually comes in when it is not UTF-8,
and whether it separates words with spaces.

Run it from the repository root after upgrading Babel, whose CLDR data gives the names, and review
the diff:

    .venv\\Scripts\\python tools\\languages.py

Sources, downloaded at the versions below:
- ISO 639-2 codes: the Library of Congress' code list (public domain).
- Names and scripts: Unicode CLDR, through Babel (Unicode License V3; the notice is in
  tools/licenses/unicode-cldr.txt).
- Which scripts have no spaces between words: CLDR's scriptMetadata.txt.
- Code pages: .NET's table of Windows locales, the same values Windows gives (MIT; the notice is in
  tools/licenses/dotnet-runtime.txt).
"""

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

from babel import Locale, UnknownLocaleError
from babel.core import get_cldr_version, get_global

CLDR_VERSION = "47"
ISO_639_URL = "https://www.loc.gov/standards/iso639-2/ISO-639-2_utf-8.txt"
SCRIPTS_URL = (
    f"https://raw.githubusercontent.com/unicode-org/cldr/release-{CLDR_VERSION}/common/properties/scriptMetadata.txt"
)
LOCALES_URL = (
    "https://raw.githubusercontent.com/dotnet/runtime/v9.0.0/"
    "src/libraries/System.Private.CoreLib/src/System/Globalization/IcuLocaleData.cs"
)
OUTPUT = Path("src/reflektortts/languages.json")

WITHOUT_SPACES = {"bo", "dz"}
"""Tibetan, whose script CLDR does not mark, has no spaces between words."""
NO_CODE_PAGE = {"ku"}
"""Windows' "ku" is Central Kurdish in Arabic script; CLDR's, and the voices', is Kurmanji."""


def main() -> None:
    if get_cldr_version() != CLDR_VERSION:
        raise SystemExit(f"Babel has CLDR {get_cldr_version()}; set CLDR_VERSION to it and check the script list.")
    codes = iso_639_codes(fetch(ISO_639_URL).decode("utf-8-sig"))
    unspaced = unspaced_scripts(fetch(SCRIPTS_URL).decode("utf-8"))
    pages = code_pages(fetch(LOCALES_URL).decode("utf-8-sig"))
    likely = get_global("likely_subtags")
    english = Locale("en")
    rows = {}
    for code, (bibliographic, terminologic) in sorted(codes.items()):
        script = likely[code].split("_")[1] if code in likely else None
        page = None if code in NO_CODE_PAGE else pages.get(f"{code}-{script}".lower(), pages.get(code))
        rows[code] = {
            "name": display_name(own_name(code) or english.languages[code]),
            "english_name": english.languages[code],
            "iso639_2b": bibliographic,
            "iso639_2t": terminologic,
            "code_page": f"cp{page}" if page else None,
            "separates_words": code not in WITHOUT_SPACES and script not in unspaced,
        }
    lines = [f"  {json.dumps(code)}: {json.dumps(row, ensure_ascii=False)}" for code, row in rows.items()]
    OUTPUT.write_bytes(("{\n" + ",\n".join(lines) + "\n}\n").encode("utf-8"))
    print(f"{len(rows)} languages written to {OUTPUT}")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "reflektortts-tools"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def iso_639_codes(text: str) -> dict[str, tuple[str, str]]:
    """ISO 639-1 code to its ISO 639-2 bibliographic and terminologic codes, which are the same
    for most languages (German: ger and deu)."""
    codes = {}
    for line in text.splitlines():
        bibliographic, terminologic, code, _english, _french = line.split("|")
        if code:
            codes[code] = (bibliographic, terminologic or bibliographic)
    return codes


def unspaced_scripts(text: str) -> set[str]:
    """Scripts whose lines break between letters, since there are no spaces between words."""
    scripts = set()
    for line in text.splitlines():
        if line and not line.startswith("#"):
            fields = [field.strip() for field in line.split(";")]
            if fields[7] == "YES":
                scripts.add(fields[0])
    return scripts


def code_pages(text: str) -> dict[str, int]:
    """Locale name (e.g. "de", "sr-cyrl") to its Windows code page, without those whose text is
    Unicode only."""
    row = re.compile(r"^\s*((?:0x[0-9a-f]{2},\s*){18})//\s*\d+\s*-\s*(\S+)\s*$")
    pages = {}
    for line in text.splitlines():
        if match := row.match(line):
            data = [int(byte, 16) for byte in re.findall(r"0x([0-9a-f]{2})", match.group(1))]
            page = (data[4] & 0xF0) >> 4 | data[3] << 4
            if page:
                pages[match.group(2)] = page
    if not pages:
        raise SystemExit(f"No locales found in {LOCALES_URL}: has its format changed?")
    return pages


def own_name(code: str) -> str | None:
    try:
        name = Locale.parse(code).languages.get(code)
    except UnknownLocaleError:
        return None
    return str(name) if name else None


def display_name(name: str) -> str:
    """The name as a list shows it: capitalized, as in "Polski", unless it has a capital of its own
    inside, as "isiZulu" has."""
    name = unicodedata.normalize("NFC", name)
    return name if any(letter.isupper() for letter in name[1:]) else name[:1].upper() + name[1:]


if __name__ == "__main__":
    main()
