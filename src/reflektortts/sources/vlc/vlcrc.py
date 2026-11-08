"""vlcrc, VLC's settings file: where it is, and a line editor that keeps every byte it does not
change.

VLC reads the file line by line: a line "key=value" sets an option, wherever it is (sections do
not matter), and of two lines for one key the last wins; lines starting with "#" are comments,
e.g. "#key=value" for an option left at its default. The file is edited as bytes, since what
ReflektorTTS writes is ASCII and a hand-edited file may be in any encoding.
"""

from pathlib import Path

import platformdirs

BOM = b"\xef\xbb\xbf"


def vlcrc_path() -> Path:
    """Where the installed VLC keeps its settings: %APPDATA%\\vlc\\vlcrc on Windows,
    ~/.config/vlc/vlcrc (or under $XDG_CONFIG_HOME) on Linux."""
    return platformdirs.user_config_path("vlc", appauthor=False, roaming=True) / "vlcrc"


def _content(line: bytes) -> bytes:
    """The line without its ending."""
    return line.rstrip(b"\r\n")


class Vlcrc:
    """The lines of a vlcrc, each kept with its own ending."""

    def __init__(self, data: bytes) -> None:
        self._bom = data.startswith(BOM)
        self._lines = data.removeprefix(BOM).splitlines(keepends=True)

    def value(self, key: str) -> bytes | None:
        """The value VLC uses for key, or None if no line sets it (VLC then uses its default)."""
        index = self._effective(key)
        if index is None:
            return None
        return _content(self._lines[index])[len(key) + 1 :]

    def values(self, key: str) -> list[str]:
        """The entries of a colon-separated module list, such as extraintf, in lowercase."""
        value = (self.value(key) or b"").decode("ascii", errors="replace")
        return [entry.strip().lower() for entry in value.split(":") if entry.strip()]

    def set(self, key: str, value: bytes) -> bytes | None:
        """Sets key to value in place of the line that sets it, or else its first commented line,
        or else in a line added at the end. Returns the line replaced, without its ending, or None
        if one was added."""
        if b"\r" in value or b"\n" in value:
            raise ValueError(f"A value for {key} in VLC's settings cannot span lines.")
        line = key.encode("ascii") + b"=" + value
        index = self._effective(key)
        if index is None:
            index = self._first(b"#" + key.encode("ascii") + b"=")
        if index is None:
            self._end_last_line()
            self._lines.append(line + self._ending())
            return None
        original = _content(self._lines[index])
        self._replace(index, line)
        return original

    def restore(self, key: str, original: bytes | None) -> None:
        """Puts original back in place of the line that sets key, or removes that line if
        original is None (set added it)."""
        index = self._effective(key)
        if index is None:
            return
        if original is None:
            del self._lines[index]
        else:
            self._replace(index, original)

    def to_bytes(self) -> bytes:
        """The file, ending with a line break: VLC drops the last character of a file without."""
        self._end_last_line()
        return (BOM if self._bom else b"") + b"".join(self._lines)

    def _effective(self, key: str) -> int | None:
        prefix = key.encode("ascii") + b"="
        return next((i for i in reversed(range(len(self._lines))) if self._lines[i].startswith(prefix)), None)

    def _first(self, prefix: bytes) -> int | None:
        return next((i for i, line in enumerate(self._lines) if line.startswith(prefix)), None)

    def _replace(self, index: int, content: bytes) -> None:
        old = self._lines[index]
        self._lines[index] = content + old[len(_content(old)) :]

    def _ending(self) -> bytes:
        """The first line's ending, which VLC writes on every line (LF, even on Windows)."""
        if self._lines:
            first = self._lines[0]
            ending = first[len(_content(first)) :]
            if ending:
                return ending
        return b"\n"

    def _end_last_line(self) -> None:
        if self._lines and _content(self._lines[-1]) == self._lines[-1]:
            self._lines[-1] += self._ending()
