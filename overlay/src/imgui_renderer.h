#pragma once

#include <dxgi.h>

namespace reflektortts {

// Draws one ImGui frame on top of the game's back buffer.
void render_overlay_frame(IDXGISwapChain* swap_chain);

// Releases the view of the back buffer before the swap chain resizes it.
void release_overlay_render_target(IDXGISwapChain* swap_chain);

}  // namespace reflektortts
