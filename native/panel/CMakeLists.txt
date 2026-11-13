# The settings panel in a window of its own, drawn with SDL3 (the window, input and drawing) and
# ImGui's SDL3 backends. SDL is linked statically, with only its video and events parts: what the
# panel does not use is left out.
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
foreach(unused AUDIO CAMERA JOYSTICK HAPTIC HIDAPI SENSOR POWER GPU DIALOG TRAY TEST_LIBRARY TESTS EXAMPLES)
    set(SDL_${unused} OFF CACHE BOOL "" FORCE)
endforeach()
FetchContent_MakeAvailable(SDL3)
# SDL's headers, which SDL3-static takes from SDL3_Headers, are included as system headers, which
# compilers do not warn about. (CMake 3.25's FetchContent SYSTEM would do this, but the minimum is 3.24.)
get_target_property(sdl_includes SDL3_Headers INTERFACE_INCLUDE_DIRECTORIES)
set_property(TARGET SDL3_Headers APPEND PROPERTY INTERFACE_SYSTEM_INCLUDE_DIRECTORIES ${sdl_includes})

add_library(imgui-backends-panel STATIC
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdl3.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdlrenderer3.cpp)
target_include_directories(imgui-backends-panel SYSTEM PUBLIC ${imgui_SOURCE_DIR}/backends)
target_link_libraries(imgui-backends-panel PUBLIC imgui SDL3::SDL3-static)

# A windowed program, so no console opens with it.
add_executable(reflektortts-panel WIN32
    src/main.cpp
    src/arguments.cpp
    src/startup_error.cpp
    src/wakeup.cpp
    src/ui_scale.cpp
    src/window_frame.cpp
    src/placement.cpp
    src/panel_ui.cpp
    src/panel_window.cpp)
target_link_libraries(reflektortts-panel PRIVATE reflektortts-shared imgui-backends-panel reflektortts-warnings)
if(WIN32)
    # DWM tells where the window's visible frame is (window_frame.cpp).
    target_link_libraries(reflektortts-panel PRIVATE dwmapi)
endif()

if(WIN32)
    # The desktop app's icon, which SDL also gives the window.
    enable_language(RC)
    target_sources(reflektortts-panel PRIVATE src/panel.rc)
    set_source_files_properties(src/panel.rc PROPERTIES
        INCLUDE_DIRECTORIES ${PROJECT_SOURCE_DIR}/../src/reflektortts/desktop)
endif()

if(MINGW)
    # Like the overlay: no MinGW runtime DLLs to ship, and release builds keep no symbol table.
    target_link_options(reflektortts-panel PRIVATE -static $<$<CONFIG:Release>:-s>)
endif()
