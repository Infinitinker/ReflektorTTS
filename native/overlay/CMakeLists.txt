FetchContent_MakeAvailable(minhook)

if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(MINHOOK_DISASSEMBLER ${minhook_SOURCE_DIR}/src/hde/hde64.c)
else()
    set(MINHOOK_DISASSEMBLER ${minhook_SOURCE_DIR}/src/hde/hde32.c)
endif()
add_library(minhook STATIC
    ${minhook_SOURCE_DIR}/src/buffer.c
    ${minhook_SOURCE_DIR}/src/hook.c
    ${minhook_SOURCE_DIR}/src/trampoline.c
    ${MINHOOK_DISASSEMBLER})
target_include_directories(minhook PUBLIC ${minhook_SOURCE_DIR}/include)

add_library(imgui-backends-overlay STATIC
    ${imgui_SOURCE_DIR}/backends/imgui_impl_win32.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx9.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx11.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx12.cpp)
target_include_directories(imgui-backends-overlay PUBLIC ${imgui_SOURCE_DIR}/backends)
# ImGui's Direct3D 11 and 12 backends link dxgi.dll and d3dcompiler_47.dll, so those load
# with the overlay into every app.
target_link_libraries(imgui-backends-overlay PUBLIC imgui d3dcompiler dxgi dwmapi gdi32)

# The Direct3D and DirectInput DLLs are looked up at runtime, not linked, so the overlay
# hooks only the APIs the game has loaded.
add_library(reflektortts-overlay SHARED
    src/dllmain.cpp
    src/diagnostics/crash_log.cpp
    src/hooks/code_hook.cpp
    src/hooks/dll_load_watch.cpp
    src/hooks/probe_window.cpp
    src/hooks/dxgi_hook.cpp
    src/hooks/d3d12_queue_hook.cpp
    src/hooks/d3d9_hook.cpp
    src/renderers/overlay_frame.cpp
    src/renderers/d3d11_renderer.cpp
    src/renderers/d3d12_renderer.cpp
    src/renderers/d3d9_renderer.cpp
    src/input/panel_input.cpp
    src/input/blocking.cpp
    src/input/win32_hook.cpp
    src/input/dinput_hook.cpp
    src/ui/overlay_ui.cpp
    src/ui/subtitles.cpp)
set_target_properties(reflektortts-overlay PROPERTIES PREFIX "")
# The overlay's own headers are included by their path from src/ ("hooks/code_hook.h").
target_include_directories(reflektortts-overlay PRIVATE src)
target_link_libraries(reflektortts-overlay PRIVATE reflektortts-shared imgui-backends-overlay minhook dxguid)

add_executable(reflektortts-inject injector/inject.cpp)

if(MINGW)
    # The game folder has no MinGW runtime DLLs, so link them in. The DLL exports only the entry
    # point the injector starts it with, by its plain name (--kill-at drops 32-bit stdcall's "@4"),
    # and release builds keep no symbol table.
    target_link_options(reflektortts-overlay PRIVATE -static -Wl,--exclude-all-symbols -Wl,--kill-at
                        $<$<CONFIG:Release>:-s>)
    target_link_options(reflektortts-inject PRIVATE -static -municode $<$<CONFIG:Release>:-s>)
endif()
