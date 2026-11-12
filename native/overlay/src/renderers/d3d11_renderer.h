// Drawing the overlay on a Direct3D 11 swap chain, called just before the app shows each
// frame.

#pragma once

#include <dxgi.h>

namespace reflektortts {

// Draws the overlay on a Direct3D 11 swap chain; ignores swap chains of other APIs.
void render_d3d11_frame(IDXGISwapChain* swap_chain);

}  // namespace reflektortts
