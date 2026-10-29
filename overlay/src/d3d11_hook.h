#pragma once

#include <dxgi.h>

namespace reflektortts {

using SwapChainCallback = void (*)(IDXGISwapChain* swap_chain);

// Hooks IDXGISwapChain::Present and ResizeBuffers for every swap chain in the process.
// on_present runs just before each frame is shown; before_resize runs before the
// back buffers are resized, so views of them can be released.
bool install_d3d11_hooks(SwapChainCallback on_present, SwapChainCallback before_resize);

}  // namespace reflektortts
