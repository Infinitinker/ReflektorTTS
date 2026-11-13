"""Checks that the C++ code in native/ includes its own headers only in the directions native/README.md
writes down:

- shared/ includes nothing from overlay/ or panel/, and panel/ nothing from overlay/;
- the overlay's own headers are included by their path from overlay/src/ ("hooks/code_hook.h");
- in overlay/src/, each folder includes only from itself and the folders listed above it, in the order
  of OVERLAY_FOLDERS, while dllmain.cpp, at the top, ties them together;
- the injector includes from overlay/src/ only the memory/ helpers.

Run it from the repository root:
    python tools/check_includes.py
It names every include that goes the wrong way, or that it cannot find, and then exits with 1.
"""

import re
import sys
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import NamedTuple

NATIVE = Path("native")
PARTS = ("shared", "overlay", "panel")
"""The three parts of the native code, each a folder of native/."""
ALLOWED_PARTS = {"shared": {"shared"}, "overlay": {"overlay", "shared"}, "panel": {"panel", "shared"}}
"""The parts each part may include from."""
INCLUDE_DIRECTORIES = {"shared": ["shared"], "overlay": ["overlay/src", "shared"], "panel": ["shared"]}
"""Where the compiler looks for each part's includes besides the including file's own folder, as in the
CMakeLists.txt files: the overlay's src/, and the shared library, which the overlay and the panel link."""
OVERLAY_FOLDERS = ("memory", "diagnostics", "hooks", "input", "ui", "renderers")
"""The overlay's folders in overlay/src/, in the order native/README.md lists them: each includes only
from itself and the folders before it."""
INJECTOR_FOLDER = "memory"
"""The one folder of overlay/src/ the injector, which is outside it, includes from."""
SOURCES = {".cpp", ".h", ".hpp"}
INCLUDE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]')


class Problem(NamedTuple):
    """An include that goes the wrong way, or that cannot be found."""

    path: PurePosixPath
    """The file, relative to native/."""
    line: int
    """The include's line; 0 for a problem with the file itself."""
    include: str
    """The include as written, with its quotes or angle brackets; empty for a problem with the file."""
    reason: str

    def __str__(self) -> str:
        if not self.line:
            return f"native/{self.path}: {self.reason}"
        return f"native/{self.path}:{self.line}: {self.include} {self.reason}"


def sources(native: Path) -> Iterator[PurePosixPath]:
    """The C++ files of the three parts, relative to native/, leaving out build folders (a folder whose
    name starts with "build", and _deps), whatever the files in them are called."""
    for part in PARTS:
        for path in sorted((native / part).rglob("*")):
            relative = PurePosixPath(path.relative_to(native).as_posix())
            if path.suffix in SOURCES and not any(
                name.startswith("build") or name == "_deps" for name in relative.parent.parts
            ):
                yield relative


def resolve(native: Path, source: PurePosixPath, name: str, quoted: bool) -> PurePosixPath | None:
    """The project header an include names, relative to native/, as the compiler finds it: for a quoted
    include, first next to the including file, then in the part's include directories. None if it is
    none of the project's headers."""
    folders = [source.parent] if quoted else []
    folders += [PurePosixPath(folder) for folder in INCLUDE_DIRECTORIES[source.parts[0]]]
    for folder in folders:
        candidate = folder / name
        if (native / candidate).is_file():
            return PurePosixPath(*_normalized(candidate.parts))
    return None


def _normalized(parts: tuple[str, ...]) -> list[str]:
    """A path's parts with each folder/.. taken out."""
    result: list[str] = []
    for part in parts:
        if part == ".." and result:
            result.pop()
        elif part != ".":
            result.append(part)
    return result


def overlay_folder(path: PurePosixPath) -> str | None:
    """The folder of overlay/src/ a file is in: "" for one directly in src/ (dllmain.cpp), None for one
    outside src/ (the injector)."""
    if path.parts[:2] != ("overlay", "src"):
        return None
    return path.parts[2] if len(path.parts) > 3 else ""


def judge(source: PurePosixPath, include: str, header: PurePosixPath) -> str | None:
    """Why including the header from the source goes the wrong way; None if it does not."""
    part, header_part = source.parts[0], header.parts[0]
    if header_part not in ALLOWED_PARTS[part]:
        return f"is in {header_part}/, which {part}/ does not include from"
    folder, header_folder = overlay_folder(source), overlay_folder(header)
    if header_folder is None:
        return None
    from_src = header.relative_to("overlay/src").as_posix()
    if include[1:-1] != from_src:
        return f'is the overlay\'s own header, included by its path from overlay/src/: "{from_src}"'
    if folder is None:
        if header_folder != INJECTOR_FOLDER:
            return f"is not in overlay/src/{INJECTOR_FOLDER}/, the one folder the injector includes from"
        return None
    if folder == "":
        return None
    if header_folder == "":
        return f"is directly in overlay/src/, which only dllmain.cpp there ties together; {folder}/ includes none"
    if folder not in OVERLAY_FOLDERS or header_folder not in OVERLAY_FOLDERS:
        return None  # problems() names every file in a folder that is not in the order
    allowed = OVERLAY_FOLDERS[: OVERLAY_FOLDERS.index(folder) + 1]
    if header_folder not in allowed:
        listed = ", ".join(f"{name}/" for name in allowed)
        return f"is in {header_folder}/, listed below {folder}/, which includes only from {listed}"
    return None


def problems(native: Path) -> list[Problem]:
    """Every include in the native code that goes the wrong way or that cannot be found."""
    found = []
    for source in sources(native):
        folder = overlay_folder(source)
        if folder and folder not in OVERLAY_FOLDERS:
            reason = (
                f"is in overlay/src/{folder}/, which is not in OVERLAY_FOLDERS: add it there and to native/README.md"
            )
            found.append(Problem(source, 0, "", reason))
        text = (native / source).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            match = INCLUDE.match(line)
            if not match:
                continue
            quoted = match.group(1) == '"'
            include = f'"{match.group(2)}"' if quoted else f"<{match.group(2)}>"
            header = resolve(native, source, match.group(2), quoted)
            if header is None:
                if quoted:
                    unknown = "is none of the project's headers: include system and library headers with <>"
                    found.append(Problem(source, number, include, unknown))
            elif wrong := judge(source, include, header):
                found.append(Problem(source, number, include, wrong))
    return found


def main() -> None:
    if not NATIVE.is_dir():
        raise SystemExit("Run this from the repository root, which has the native/ folder.")
    found = problems(NATIVE)
    if found:
        print("\n".join(str(problem) for problem in found))
        print(f"\n{len(found)} problems with the include directions in native/README.md.")
        sys.exit(1)
    print("Every include in native/ follows the directions in native/README.md.")


if __name__ == "__main__":
    main()
