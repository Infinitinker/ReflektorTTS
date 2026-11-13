// Scales ImGui to the display the window is on: how much bigger than at 100% the display wants the
// window's contents, and ImGui's style and fonts scaled by that.

#pragma once

#include <SDL3/SDL_video.h>
#include <imgui.h>

namespace reflektortts {

// How much bigger than at 100% the display wants the window's contents, in window coordinates:
// its display scale without the pixel density, which ImGui's SDL3 backend applies by itself.
float window_ui_scale(SDL_Window* window);

// Scales ImGui's sizes and fonts by scale, starting again from base, the style before any scaling.
void apply_ui_scale(const ImGuiStyle& base, float scale);

}  // namespace reflektortts
