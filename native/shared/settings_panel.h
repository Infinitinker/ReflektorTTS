#pragma once

#include "core_state.h"

namespace reflektortts {

// Where the settings panel is drawn, which decides what it shows besides the profile's settings.
enum class PanelPlace {
    // Over the app being read: whether reading is active or paused, the buttons to pause it and
    // to stop the line, and the last line read.
    Overlay,
    // In a window of its own, for one profile: whether its app is being read.
    Window,
};

// The overlay panel's width, its window padding included. The panel's own window opens wide
// enough to show the contents as wide as there, with room for a scrollbar besides. The desktop app
// knows that window's width too, to choose the side it opens on: change PANEL_WIDTH in
// src/reflektortts/desktop/panel/dock.py with it.
inline constexpr float kSettingsPanelWidth = 420.0f;

// The settings panel's contents, in the current ImGui window: a header with the connection state,
// then, while connected, the app and the Input, Processing and Output boxes (and in the overlay,
// the Last line box), or why the profile's settings cannot be shown; then the last error with a
// button to dismiss it.
void draw_settings_panel(const CoreState& state, PanelPlace place);

}  // namespace reflektortts
