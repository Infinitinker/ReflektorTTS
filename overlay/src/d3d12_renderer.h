#pragma once

#include <dxgi.h>

namespace reflektortts {

// Draws the overlay on a Direct3D 12 swap chain; ignores swap chains of other APIs.
// Waits until the app's command queue is known (see d3d12_queue_hook.h).
void render_d3d12_frame(IDXGISwapChain* swap_chain);

}  // namespace reflektortts
