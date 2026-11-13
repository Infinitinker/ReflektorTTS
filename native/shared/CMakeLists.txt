# What does not depend on where it is drawn or on the OS: the API client and the settings panel's
# drawing, shared by the overlay and the panel. The transport is one file per OS.
add_library(reflektortts-shared STATIC
    log.cpp
    system_font.cpp
    api_client.cpp
    widgets.cpp
    text_fit.cpp
    processing_section.cpp
    settings_panel.cpp)
target_include_directories(reflektortts-shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(reflektortts-shared PUBLIC imgui nlohmann_json::nlohmann_json PRIVATE reflektortts-warnings)

if(WIN32)
    target_sources(reflektortts-shared PRIVATE transport_winhttp.cpp)
    target_link_libraries(reflektortts-shared PUBLIC winhttp)
endif()
