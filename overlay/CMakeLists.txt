cmake_minimum_required(VERSION 3.24)
project(reflektortts_overlay LANGUAGES C CXX)

if(NOT WIN32)
    message(FATAL_ERROR "The overlay is Windows-only for now.")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

include(FetchContent)
FetchContent_Declare(imgui
    GIT_REPOSITORY https://github.com/ocornut/imgui.git
    GIT_TAG v1.92.9
    GIT_SHALLOW TRUE)
FetchContent_Declare(nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.12.0
    GIT_SHALLOW TRUE)
# MinHook's own CMake project builds a DLL with resources; only its sources are used here.
FetchContent_Declare(minhook
    GIT_REPOSITORY https://github.com/TsudaKageyu/minhook.git
    GIT_TAG v1.3.4
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR not-built-with-its-cmake)
FetchContent_MakeAvailable(imgui nlohmann_json minhook)

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

add_library(imgui STATIC
    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_win32.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx9.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx11.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_dx12.cpp)
target_include_directories(imgui PUBLIC ${imgui_SOURCE_DIR} ${imgui_SOURCE_DIR}/backends)
target_link_libraries(imgui PUBLIC d3dcompiler dxgi dwmapi imm32 gdi32)

# Direct3D and DirectInput DLLs are looked up at runtime, not linked, so the overlay
# only touches the APIs the game has loaded.
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
    src/api_client.cpp
    src/ui.cpp)
set_target_properties(reflektortts-overlay PROPERTIES PREFIX "")
target_link_libraries(reflektortts-overlay PRIVATE imgui nlohmann_json::nlohmann_json minhook winhttp dxguid)

add_executable(reflektortts-inject injector/inject.cpp)

if(MINGW)
    # The game folder has no MinGW runtime DLLs, so link them in.
    target_link_options(reflektortts-overlay PRIVATE -static)
    target_link_options(reflektortts-inject PRIVATE -static -municode)
endif()
