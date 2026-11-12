// Sizes the window and places it where it opens: beside the desktop app's window, or centered on
// the main display.

#include "placement.h"

#include <algorithm>
#include <cmath>

#include "settings_panel.h"
#include "ui_scale.h"
#include "window_frame.h"

namespace reflektortts {
namespace {

// The height when the desktop app does not say where to open, at 100% display scale.
constexpr float kDefaultHeight = 600.0f;

int rounded(float value) {
    return static_cast<int>(std::lround(value));
}

// Physical pixels per window coordinate: 1 on Windows, where SDL's window coordinates are physical
// pixels (SDL makes the process per-monitor DPI aware, and the display's scale goes into
// SDL_GetWindowDisplayScale instead); more on systems that scale window coordinates themselves.
float pixel_density(SDL_Window* window) {
    float density = SDL_GetWindowPixelDensity(window);
    return density > 0.0f ? density : 1.0f;
}

}  // namespace

WindowSize place_window(SDL_Window* window, const std::optional<Dock>& dock, float scrollbar_width) {
    const float width = kSettingsPanelWidth + scrollbar_width;
    if (!dock) {
        float scale = window_ui_scale(window);
        SDL_SetWindowSize(window, rounded(width * scale), rounded(kDefaultHeight * scale));
        SDL_SetWindowPosition(window, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED);
        SDL_SyncWindow(window);
        return {width, kDefaultHeight};
    }

    // Onto the desktop app's display first, whose scale sets the width. Edges are as Windows'
    // rectangles have them, a right edge being the first pixel past it: dock->x is the panel's first
    // pixel on the right, and one past its last on the left, so the panel's pixel next to the edge,
    // on the display it fits on, is dock->x or dock->x - 1. On the left that may be the desktop
    // window's display's right edge, with another display next to it, so the window is centered on
    // that pixel's display rather than moved to it, which would put it on the other display.
    float density = pixel_density(window);
    const int inside_x = dock->side == DockSide::Right ? dock->x : dock->x - 1;
    const SDL_Point inside{rounded(static_cast<float>(inside_x) / density),
                           rounded(static_cast<float>(dock->y + dock->height / 2) / density)};
    SDL_DisplayID display = SDL_GetDisplayForPoint(&inside);
    if (display == 0) {
        display = SDL_GetPrimaryDisplay();
    }
    SDL_SetWindowPosition(window, static_cast<int>(SDL_WINDOWPOS_CENTERED_DISPLAY(display)),
                          static_cast<int>(SDL_WINDOWPOS_CENTERED_DISPLAY(display)));
    SDL_SyncWindow(window);
    const float scale = window_ui_scale(window);
    density = pixel_density(window);

    // The dock is measured on the visible frame, and SDL places the client area: the frame's
    // insets, in physical pixels, make up the difference.
    const FrameInsets frame = visible_frame_insets(window);
    const int client_width = rounded(width * scale);
    const int frame_width = rounded(static_cast<float>(client_width) * density) + frame.left + frame.right;
    const int left = dock->side == DockSide::Right ? dock->x : dock->x - frame_width;
    const int client_height =
        std::max(1, rounded(static_cast<float>(dock->height - frame.top - frame.bottom) / density));
    SDL_SetWindowSize(window, client_width, client_height);
    SDL_SetWindowPosition(window, rounded(static_cast<float>(left + frame.left) / density),
                          rounded(static_cast<float>(dock->y + frame.top) / density));
    SDL_SyncWindow(window);
    return {width, static_cast<float>(client_height) / scale};
}

}  // namespace reflektortts
