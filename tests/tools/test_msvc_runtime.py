"""The Visual C++ runtime in a release: taken from one place, one version, new enough for the binaries
that import it, with the Universal C Runtime left out."""

from pathlib import Path

import pytest
from msvc_runtime import RUNTIME, RuntimeSourceError, check_versions, install_runtime, required_toolset

NEW = (14, 51, 36247, 0)
OLD = (14, 40, 33816, 0)


def test_one_version_new_enough_is_taken() -> None:
    assert check_versions(dict.fromkeys(RUNTIME, NEW), (14, 44)) == NEW


def test_a_missing_dll_is_named() -> None:
    versions: dict[str, tuple[int, int, int, int] | None] = {**dict.fromkeys(RUNTIME, NEW), "msvcp140_1.dll": None}

    with pytest.raises(RuntimeSourceError, match=r"msvcp140_1\.dll not found .*install the latest"):
        check_versions(versions, None)


def test_a_mix_of_versions_is_refused() -> None:
    with pytest.raises(RuntimeSourceError, match="a mix of versions"):
        check_versions({**dict.fromkeys(RUNTIME, NEW), "msvcp140.dll": OLD}, None)


def test_a_runtime_older_than_a_binary_s_toolset_is_refused() -> None:
    with pytest.raises(RuntimeSourceError, match=r"14\.40\.33816\.0, older than the toolset 14\.51"):
        check_versions(dict.fromkeys(RUNTIME, OLD), (14, 51))


def test_the_newest_toolset_among_the_binaries_that_import_the_runtime_is_required() -> None:
    toolsets = {"onnxruntime.dll": (14, 44), "sentencepiece.pyd": (14, 51), "cudnn.dll": None}

    assert required_toolset([Path(name) for name in toolsets], lambda path: toolsets[path.name]) == (14, 51)
    assert required_toolset([Path("cudnn.dll")], lambda path: None) is None


def test_the_build_gets_the_runtime_from_its_source_and_no_universal_c_runtime(tmp_path: Path) -> None:
    internal = tmp_path / "_internal"
    source = tmp_path / "System32"
    internal.mkdir()
    source.mkdir()
    for name in ("api-ms-win-crt-heap-l1-1-0.dll", "ucrtbase.dll", "MSVCP140_1.dll", "vcruntime140.dll", "app.pyd"):
        (internal / name).write_text("collected")
    for name in RUNTIME:
        (source / name).write_text("redistributable")

    def toolset(path: Path) -> tuple[int, int] | None:
        return (14, 44) if path.suffix == ".pyd" else None

    version = install_runtime(internal, source, lambda path: NEW, toolset)

    assert version == NEW
    assert sorted(path.name for path in internal.iterdir()) == sorted([*RUNTIME, "app.pyd"])
    assert all((internal / name).read_text() == "redistributable" for name in RUNTIME)
