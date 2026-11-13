cmake_minimum_required(VERSION 3.24)
project(reflektortts_native LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# Each dependency is pinned to the commit of a release tag, since a tag can be moved.
include(FetchContent)
FetchContent_Declare(imgui
    GIT_REPOSITORY https://github.com/ocornut/imgui.git
    GIT_TAG 01380c579715e62fb9a8d6ec0502c4ea83bfde6e) # v1.92.9
FetchContent_Declare(nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG 55f93686c01528224f448c19128836e7df245f72) # v3.12.0
# MinHook's own CMake project builds a DLL with resources; only its sources are used, by the overlay.
FetchContent_Declare(minhook
    GIT_REPOSITORY https://github.com/TsudaKageyu/minhook.git
    GIT_TAG c3fcafdc10146beb5919319d0683e44e3c30d537 # v1.3.4
    SOURCE_SUBDIR not-built-with-its-cmake)
# For the panel's window only.
FetchContent_Declare(SDL3
    GIT_REPOSITORY https://github.com/libsdl-org/SDL.git
    GIT_TAG f00dc919ca35b9756316e86c4777392de442f9b2) # release-3.4.20
# nlohmann_json's headers are included as system headers, which compilers do not warn about.
set(JSON_SystemInclude ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(imgui nlohmann_json)

# ImGui's core; each part adds the platform and renderer backends it draws with.
add_library(imgui STATIC
    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp)
target_include_directories(imgui SYSTEM PUBLIC ${imgui_SOURCE_DIR})
# ReflektorTTS's windows open no links, so they need none of ImGui's shell calls (ShellExecuteW).
target_compile_definitions(imgui PUBLIC IMGUI_DISABLE_DEFAULT_SHELL_FUNCTIONS)
if(WIN32)
    # ImGui's default text input method (IME) handling on Windows.
    target_link_libraries(imgui PUBLIC imm32)
endif()

# The compiler's warnings, for ReflektorTTS's own code, which links this target. The fetched libraries'
# headers (ImGui, its backends, MinHook, nlohmann_json and SDL) are included as system headers, which
# compilers do not warn about. The ci preset makes the
# warnings errors. Left out: -Wuseless-cast, since a cast needed in one build is useless in the
# other (DWORD and the like differ between 32 and 64 bits); -Wmissing-declarations, which asks for
# declarations of the entry points (DllMain, wmain) that nothing else calls; and GCC's own
# -Wduplicated-cond, -Wduplicated-branches and -Wlogical-op, which clang-tidy, reading the same
# commands with Clang, rejects as unknown once they are errors.
option(REFLEKTORTTS_WARNINGS_AS_ERRORS "Treat the compiler's warnings in ReflektorTTS's own code as errors" OFF)
add_library(reflektortts-warnings INTERFACE)
target_compile_options(reflektortts-warnings INTERFACE
    -Wall -Wextra -Wpedantic -Wformat=2 -Wshadow -Wnon-virtual-dtor -Woverloaded-virtual -Wcast-align -Wcast-qual
    -Wnull-dereference -Wimplicit-fallthrough -Wundef -Wconversion -Wsign-conversion -Wold-style-cast
    -Wdouble-promotion
    $<$<BOOL:${REFLEKTORTTS_WARNINGS_AS_ERRORS}>:-Werror>)

add_subdirectory(shared)
if(WIN32)
    add_subdirectory(overlay)
endif()
# The panel reaches the core through the shared library's transport, which exists for Windows only.
# 32-bit builds are for the overlay in 32-bit apps, so only the 64-bit build makes the panel.
if(WIN32 AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    add_subdirectory(panel)
elseif(WIN32)
    message(STATUS "The panel is not built: it comes with the 64-bit build only")
else()
    message(STATUS "The panel is not built: it needs a transport for this system (see shared/transport.h)")
endif()
