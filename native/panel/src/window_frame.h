// Measures the window's visible frame: the title bar and the borders the user sees around its
// client area.

#pragma once

#include <SDL3/SDL_video.h>

namespace reflektortts {

// How far the window's visible frame reaches past its client area on each side, in physical
// pixels: the title bar and the borders the user sees.
struct FrameInsets {
    int left = 0;
    int top = 0;
    int right = 0;
    int bottom = 0;
};

// The window's visible frame. On Windows it leaves out the invisible borders Windows puts around a
// resizable window for grabbing its edges, which SDL_GetWindowBordersSize counts; elsewhere it is
// SDL's borders. Zero on each side where it cannot be told.
FrameInsets visible_frame_insets(SDL_Window* window);

}  // namespace reflektortts
