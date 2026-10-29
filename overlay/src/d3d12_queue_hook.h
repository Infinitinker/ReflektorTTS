#pragma once

#include <d3d12.h>

namespace reflektortts {

// Hooks ID3D12CommandQueue::ExecuteCommandLists to find the game's direct command queue,
// which the overlay needs to submit its own drawing. Requires d3d12.dll to be loaded.
bool install_d3d12_queue_hook();

// The first direct queue the game submitted work to, or nullptr until it has.
ID3D12CommandQueue* game_command_queue();

}  // namespace reflektortts
