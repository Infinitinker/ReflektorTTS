#pragma once

#include <d3d9.h>

namespace reflektortts {

// Draws the overlay on a Direct3D 9 device's back buffer.
void render_d3d9_frame(IDirect3DDevice9* device);

// Release and recreate the overlay's device objects around IDirect3DDevice9::Reset.
void release_d3d9_device_objects(IDirect3DDevice9* device);
void recreate_d3d9_device_objects(IDirect3DDevice9* device);

}  // namespace reflektortts
