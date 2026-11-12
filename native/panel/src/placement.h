// Where the panel's window opens and at what size: beside the desktop app's window or centered on
// the main display, wide enough for the settings panel. That size is also its smallest.

#pragma once

#include <SDL3/SDL_video.h>

#include <optional>

#include "arguments.h"

namespace reflektortts {

// A window's client area at 100% display scale, in window coordinates.
struct WindowSize {
    float width = 0.0f;
    float height = 0.0f;
};

// Sizes and moves the window, not shown yet, to where it opens: beside the desktop app's window as
// dock says, as tall as it, or else centered on the main display, 600 high. Either way it is wide
// enough to show the overlay panel's contents (kSettingsPanelWidth) besides a scrollbar of
// scrollbar_width, ImGui's at 100%. Returns the size it opens at, which is also its smallest.
WindowSize place_window(SDL_Window* window, const std::optional<Dock>& dock, float scrollbar_width);

}  // namespace reflektortts
