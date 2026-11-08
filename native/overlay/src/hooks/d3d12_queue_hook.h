#pragma once

#include <d3d12.h>

namespace reflektortts {

// Hooks ID3D12CommandQueue::ExecuteCommandLists to find the app's direct command queue,
// which the overlay needs to submit its own drawing. Requires d3d12.dll to be loaded.
bool install_d3d12_queue_hook();

// The first direct queue of `device` the app submitted work to, or nullptr until it has.
// On a device with several direct queues it may not be the one the app presents from.
ID3D12CommandQueue* app_command_queue(ID3D12Device* device);

}  // namespace reflektortts
