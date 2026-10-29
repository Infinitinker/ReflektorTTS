#pragma once

#include <d3d9.h>

namespace reflektortts {

using DeviceCallback = void (*)(IDirect3DDevice9* device);

// Hooks IDirect3DDevice9::Present and Reset for every Direct3D 9 device in the process.
// on_present runs just before each frame is shown; before_reset and after_reset bracket
// a successful device reset, so device objects can be released and recreated.
// Requires d3d9.dll to be loaded.
bool install_d3d9_hooks(DeviceCallback on_present, DeviceCallback before_reset, DeviceCallback after_reset);

}  // namespace reflektortts
