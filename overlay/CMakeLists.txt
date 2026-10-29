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
FetchContent_MakeAvailable(imgui)

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

# Direct3D DLLs are looked up at runtime, not linked, so the overlay only touches
# the APIs the game has loaded.
add_library(reflektortts-overlay SHARED
    src/dllmain.cpp
    src/probe_window.cpp
    src/dxgi_hook.cpp
    src/d3d11_renderer.cpp
    src/d3d12_queue_hook.cpp
    src/d3d12_renderer.cpp
    src/d3d9_hook.cpp
    src/d3d9_renderer.cpp
    src/overlay_frame.cpp
    src/ui.cpp)
set_target_properties(reflektortts-overlay PROPERTIES PREFIX "")
target_link_libraries(reflektortts-overlay PRIVATE imgui)

add_executable(reflektortts-inject injector/inject.cpp)

if(MINGW)
    # The game folder has no MinGW runtime DLLs, so link them in.
    target_link_options(reflektortts-overlay PRIVATE -static)
    target_link_options(reflektortts-inject PRIVATE -static -municode)
endif()
