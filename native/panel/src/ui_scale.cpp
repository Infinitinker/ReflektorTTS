// Scales ImGui to the display: the display's scale without the pixel density, which ImGui's SDL3
// backend applies by itself, and ImGui's style and fonts scaled from their sizes at 100%.

#include "ui_scale.h"

namespace reflektortts {

float window_ui_scale(SDL_Window* window) {
    float display_scale = SDL_GetWindowDisplayScale(window);
    float pixel_density = SDL_GetWindowPixelDensity(window);
    if (display_scale <= 0.0f || pixel_density <= 0.0f) {
        return 1.0f;
    }
    return display_scale / pixel_density;
}

void apply_ui_scale(const ImGuiStyle& base, float scale) {
    ImGuiStyle& style = ImGui::GetStyle();
    style = base;
    style.ScaleAllSizes(scale);
    style.FontScaleDpi = scale;
}

}  // namespace reflektortts
