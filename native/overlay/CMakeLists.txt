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
    src/crash_log.cpp
    src/dll_load_watch.cpp
    src/probe_window.cpp
    src/dxgi_hook.cpp
    src/d3d11_renderer.cpp
    src/d3d12_queue_hook.cpp
    src/d3d12_renderer.cpp
    src/d3d9_hook.cpp
    src/d3d9_renderer.cpp
    src/overlay_frame.cpp
    src/input.cpp
    src/code_hook.cpp
    src/input_blocking.cpp
    src/win32_input_hook.cpp
    src/dinput_hook.cpp
    src/subtitles.cpp
    src/ui.cpp)
set_target_properties(reflektortts-overlay PROPERTIES PREFIX "")
target_link_libraries(reflektortts-overlay PRIVATE reflektortts-shared imgui-backends-overlay minhook dxguid)

add_executable(reflektortts-inject injector/inject.cpp)

if(MINGW)
    # The game folder has no MinGW runtime DLLs, so link them in. The DLL needs no exports
    # (the injector only loads it), and release builds keep no symbol table.
    target_link_options(reflektortts-overlay PRIVATE -static -Wl,--exclude-all-symbols $<$<CONFIG:Release>:-s>)
    target_link_options(reflektortts-inject PRIVATE -static -municode $<$<CONFIG:Release>:-s>)
endif()
