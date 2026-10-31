#pragma once

#include <d3d9.h>

namespace reflektortts {

using DeviceCallback = void (*)(IDirect3DDevice9* device);

// Hooks IDirect3DDevice9::Present and Reset of the game's Direct3D 9 devices. on_present runs
// just before each frame is shown; before_reset and after_reset bracket a successful device
// reset, so device objects can be released and recreated. Requires d3d9.dll to be loaded.
//
// Devices are hooked as the game creates them. device_may_exist says the game may have made its
// device before the overlay arrived, which a throwaway probe device then finds; at the game's
// start that is skipped, since some games (GTA San Andreas) are in a launcher dialog or own the
// screen, where probing fails or interferes.
bool install_d3d9_hooks(DeviceCallback on_present, DeviceCallback before_reset, DeviceCallback after_reset,
                        bool device_may_exist);

}  // namespace reflektortts
