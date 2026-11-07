#pragma once

#include <string>

#include "core_state.h"

namespace reflektortts {

// The settings panel in one ImGui window that fills the SDL window, with no title bar of its own.
void draw_panel_ui(const CoreState& state);

// The SDL window's title: "<app title> settings - ReflektorTTS", or "Settings - ReflektorTTS"
// while the app is not known.
std::string window_title(const CoreState& state);

}  // namespace reflektortts
