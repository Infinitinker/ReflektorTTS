"""The include check: finding the headers includes name as the compiler does, and each direction
native/README.md writes down, on a small native/ folder of its own and on the real one."""

from pathlib import Path

from check_includes import problems

NATIVE = Path(__file__).parents[2] / "native"


def write(native: Path, files: dict[str, str]) -> Path:
    """Writes the files, each given as its path in native/ and its include lines."""
    for name, text in files.items():
        path = native / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return native


def found(native: Path) -> list[str]:
    return [str(problem) for problem in problems(native)]


def test_the_real_native_code_follows_the_directions() -> None:
    assert found(NATIVE) == []


def test_includes_that_follow_the_directions_pass(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {
            "shared/log.h": "#include <string>\n",
            "shared/api_client.h": '#include "log.h"\n',
            "overlay/src/dllmain.cpp": '#include "hooks/code_hook.h"\n#include "ui/overlay_ui.h"\n#include "log.h"\n',
            "overlay/src/diagnostics/crash_log.h": "#include <windows.h>\n",
            "overlay/src/hooks/code_hook.h": '#include "diagnostics/crash_log.h"\n',
            "overlay/src/hooks/code_hook.cpp": '#include "hooks/code_hook.h"\n#include "log.h"\n',
            "overlay/src/ui/overlay_ui.h": '#include "hooks/code_hook.h"\n#include <api_client.h>\n',
            "overlay/src/memory/addresses.h": "",
            "overlay/injector/inject.cpp": '#include <windows.h>\n#include "memory/addresses.h"\n',
            "panel/src/main.cpp": '#include "arguments.h"\n#include "api_client.h"\n',
            "panel/src/arguments.h": "#include <optional>\n",
        },
    )
    assert found(native) == []


def test_the_shared_library_includes_nothing_from_the_overlay_or_the_panel(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {
            "shared/log.h": '#include "../overlay/src/hooks/code_hook.h"\n\n#include "../panel/src/arguments.h"\n',
            "overlay/src/hooks/code_hook.h": "",
            "panel/src/arguments.h": "",
        },
    )
    assert found(native) == [
        'native/shared/log.h:1: "../overlay/src/hooks/code_hook.h" is in overlay/, which shared/ does not include from',
        'native/shared/log.h:3: "../panel/src/arguments.h" is in panel/, which shared/ does not include from',
    ]


def test_the_panel_includes_nothing_from_the_overlay(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {"panel/src/main.cpp": '#include "../../overlay/src/ui/subtitles.h"\n', "overlay/src/ui/subtitles.h": ""},
    )
    assert found(native) == [
        'native/panel/src/main.cpp:1: "../../overlay/src/ui/subtitles.h" is in overlay/, '
        "which panel/ does not include from"
    ]


def test_an_overlay_folder_includes_only_from_folders_listed_above_it(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {
            "overlay/src/hooks/d3d9_hook.cpp": '#include "renderers/d3d9_renderer.h"\n#include "input/blocking.h"\n',
            "overlay/src/renderers/d3d9_renderer.h": "",
            "overlay/src/input/blocking.h": "",
        },
    )
    assert found(native) == [
        'native/overlay/src/hooks/d3d9_hook.cpp:1: "renderers/d3d9_renderer.h" is in renderers/, listed below hooks/, '
        "which includes only from memory/, diagnostics/, hooks/",
        'native/overlay/src/hooks/d3d9_hook.cpp:2: "input/blocking.h" is in input/, listed below hooks/, '
        "which includes only from memory/, diagnostics/, hooks/",
    ]


def test_the_overlays_headers_are_included_by_their_path_from_src(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {"overlay/src/hooks/code_hook.cpp": '#include "code_hook.h"\n', "overlay/src/hooks/code_hook.h": ""},
    )
    assert found(native) == [
        'native/overlay/src/hooks/code_hook.cpp:1: "code_hook.h" is the overlay\'s own header, '
        'included by its path from overlay/src/: "hooks/code_hook.h"'
    ]


def test_only_dllmain_includes_what_is_directly_in_src(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {"overlay/src/ui/overlay_ui.cpp": '#include "frame.h"\n', "overlay/src/frame.h": ""},
    )
    assert found(native) == [
        'native/overlay/src/ui/overlay_ui.cpp:1: "frame.h" is directly in overlay/src/, which only dllmain.cpp '
        "there ties together; ui/ includes none"
    ]


def test_the_injector_includes_only_the_memory_helpers(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {
            "overlay/injector/inject.cpp": '#include "memory/addresses.h"\n#include "hooks/code_hook.h"\n',
            "overlay/src/memory/addresses.h": "",
            "overlay/src/hooks/code_hook.h": "",
        },
    )
    assert found(native) == [
        'native/overlay/injector/inject.cpp:2: "hooks/code_hook.h" is not in overlay/src/memory/, '
        "the one folder the injector includes from"
    ]


def test_a_folder_missing_from_the_order_is_named(tmp_path: Path) -> None:
    native = write(tmp_path, {"overlay/src/capture/frames.cpp": ""})
    assert found(native) == [
        "native/overlay/src/capture/frames.cpp: is in overlay/src/capture/, which is not in OVERLAY_FOLDERS: "
        "add it there and to native/README.md"
    ]


def test_a_folder_missing_from_the_order_is_named_whatever_it_includes(tmp_path: Path) -> None:
    native = write(
        tmp_path,
        {
            "overlay/src/hooks/code_hook.h": "",
            "overlay/src/capture/frames.h": "",
            "overlay/src/capture/frames.cpp": '#include "hooks/code_hook.h"\n#include "capture/frames.h"\n',
            "overlay/src/ui/overlay_ui.cpp": '#include "capture/frames.h"\n',
        },
    )
    missing = "which is not in OVERLAY_FOLDERS: add it there and to native/README.md"
    assert found(native) == [
        f"native/overlay/src/capture/frames.cpp: is in overlay/src/capture/, {missing}",
        f"native/overlay/src/capture/frames.h: is in overlay/src/capture/, {missing}",
    ]


def test_a_quoted_include_that_is_no_project_header_is_named(tmp_path: Path) -> None:
    native = write(tmp_path, {"shared/log.cpp": '#include "windows.h"\n#include <imgui.h>\n'})
    assert found(native) == [
        'native/shared/log.cpp:1: "windows.h" is none of the project\'s headers: '
        "include system and library headers with <>"
    ]


def test_build_folders_are_left_out(tmp_path: Path) -> None:
    native = write(tmp_path, {"shared/build/_deps/lib.cpp": '#include "missing.h"\n'})
    assert found(native) == []


def test_files_named_like_a_build_folder_are_checked(tmp_path: Path) -> None:
    native = write(tmp_path, {"panel/src/panel.h": "", "shared/builder.cpp": '#include "../panel/src/panel.h"\n'})
    assert found(native) == [
        'native/shared/builder.cpp:1: "../panel/src/panel.h" is in panel/, which shared/ does not include from'
    ]
