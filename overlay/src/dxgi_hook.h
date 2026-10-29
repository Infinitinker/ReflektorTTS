#pragma once

#include <dxgi.h>

namespace reflektortts {

using SwapChainCallback = void (*)(IDXGISwapChain* swap_chain);

// Hooks IDXGISwapChain::Present and IDXGISwapChain1::Present1 for every swap chain in the
// process, which covers Direct3D 10, 11 and 12. on_present runs just before each frame is shown.
bool install_dxgi_hooks(SwapChainCallback on_present);

}  // namespace reflektortts
