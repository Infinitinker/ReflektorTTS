"""Microsoft's Visual C++ runtime in a release: where its DLLs come from, and which version they must be.

Python and the native libraries of its packages (onnxruntime, CTranslate2, sentencepiece and more)
import the Visual C++ runtime (RUNTIME), so a release ships it. PyInstaller takes those DLLs, and the
Universal C Runtime's, wherever its search finds them first, PATH included, which made a release depend
on what else the build machine had installed (a JDK's older copies, say). So the release build runs
PyInstaller with PATH holding only the Windows folders (system_path), leaves out the Universal C
Runtime, which Windows 10 and later include, and puts in the four runtime DLLs from one place: the
Visual C++ redistributable installed on the build machine, in System32. They must all be one version, at
least as new as the newest Visual C++ toolset that built a shipped binary importing them, since the
runtime is compatible only with programs built by the same toolset or an older one.
"""

import os
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

RUNTIME = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll")
"""The Visual C++ runtime DLLs the release ships, by their names in lowercase."""
UCRT = ("api-ms-win-*.dll", "ucrtbase.dll")
"""The Universal C Runtime, part of Windows 10 and later, which the release leaves out."""
BINARIES = ("*.dll", "*.pyd", "*.exe")

type Version = tuple[int, int, int, int]
type Toolset = tuple[int, int]


class RuntimeSourceError(Exception):
    """The runtime DLLs cannot be taken from where they must come from."""


def windows_folder() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows"))


def runtime_source() -> Path:
    """Where the runtime DLLs come from: System32, where the Visual C++ redistributable installs them."""
    return windows_folder() / "System32"


def system_path() -> str:
    """The PATH PyInstaller runs with: the Windows folders only, so nothing else installed is taken."""
    return os.pathsep.join(str(folder) for folder in (runtime_source(), windows_folder()))


def file_version(path: Path) -> Version:
    """A Windows binary's file version, from its version resource."""
    import pefile  # Windows only, with PyInstaller.

    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    info = pe.VS_FIXEDFILEINFO[0]
    major, minor = info.FileVersionMS >> 16, info.FileVersionMS & 0xFFFF
    return major, minor, info.FileVersionLS >> 16, info.FileVersionLS & 0xFFFF


def source_versions(source: Path, version_of: Callable[[Path], Version] = file_version) -> dict[str, Version | None]:
    """The version of each of RUNTIME in source, None for one that is not there."""
    return {name: version_of(source / name) if (source / name).is_file() else None for name in RUNTIME}


def runtime_toolset(path: Path) -> Toolset | None:
    """The Visual C++ toolset (its linker's version, e.g. 14.44) a binary was built with, if it imports
    any of RUNTIME; None if it imports none."""
    import pefile

    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    imported = {entry.dll.decode("ascii", "replace").lower() for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    if not imported & set(RUNTIME):
        return None
    return pe.OPTIONAL_HEADER.MajorLinkerVersion, pe.OPTIONAL_HEADER.MinorLinkerVersion


def required_toolset(binaries: Iterable[Path], toolset_of: Callable[[Path], Toolset | None]) -> Toolset | None:
    """The newest toolset among the binaries that import the runtime; None if none does."""
    return max((toolset for path in binaries if (toolset := toolset_of(path)) is not None), default=None)


def check_versions(versions: dict[str, Version | None], required: Toolset | None) -> Version:
    """The one version all of RUNTIME have in their source (versions, by name; None for a missing
    one). Raises RuntimeSourceError if one is missing, they differ, or they are older than required."""
    missing = [name for name in RUNTIME if versions.get(name) is None]
    if missing:
        raise RuntimeSourceError(
            f"{', '.join(missing)} not found in {runtime_source()}: install the latest Visual C++ redistributable "
            "(x64), then build again."
        )
    found = {versions[name] for name in RUNTIME}
    if len(found) != 1:
        listed = ", ".join(f"{name} {'.'.join(map(str, versions[name] or ()))}" for name in RUNTIME)
        raise RuntimeSourceError(
            f"The Visual C++ runtime in {runtime_source()} is a mix of versions ({listed}): install the latest "
            "Visual C++ redistributable (x64), then build again."
        )
    version = found.pop()
    assert version is not None
    if required is not None and version[:2] < required:
        raise RuntimeSourceError(
            f"The Visual C++ runtime in {runtime_source()} is {'.'.join(map(str, version))}, older than the "
            f"toolset {required[0]}.{required[1]} the release's libraries are built with: install the latest "
            "Visual C++ redistributable (x64), then build again."
        )
    return version


def install_runtime(
    internal: Path,
    source: Path,
    version_of: Callable[[Path], Version] = file_version,
    toolset_of: Callable[[Path], Toolset | None] = runtime_toolset,
) -> Version:
    """Leaves the Universal C Runtime out of a PyInstaller build's _internal folder and puts in RUNTIME
    from source, in place of whatever PyInstaller took. Returns their version; raises RuntimeSourceError
    (see check_versions)."""
    for pattern in UCRT:
        for path in internal.glob(pattern):
            path.unlink()
    for name in RUNTIME:
        for path in internal.iterdir():
            if path.name.lower() == name:
                path.unlink()
    binaries = [path for pattern in BINARIES for path in internal.rglob(pattern)]
    version = check_versions(source_versions(source, version_of), required_toolset(binaries, toolset_of))
    for name in RUNTIME:
        shutil.copy2(source / name, internal / name)
    return version
