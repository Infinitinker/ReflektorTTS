#pragma once

#include <windows.h>

namespace reflektortts {

// Gives the overlay to the first graphics API that presents a frame, creating the ImGui
// context and the Win32 platform backend for its window. Returns false if another API
// already owns the overlay or setup fails.
bool claim_overlay(const char* api_name, HWND window);

// Moves the Win32 platform backend to another window, e.g. when the game recreates it.
void set_overlay_window(HWND window);

// Detaches the renderer backend from a device the game has replaced, without releasing
// anything created on it. Games and wrappers may destroy a device while the overlay still
// holds references, so touching it again could crash the game. The backend's few objects
// are leaked; textures are recreated by the next backend.
void forget_renderer_backend();

// Runs the platform and UI half of an ImGui frame. Call it after the renderer backend's
// NewFrame and before its RenderDrawData. The frame is laid out in back buffer pixels,
// which can differ from the window's size when the game or a wrapper scales its image.
void build_overlay_frame(UINT back_buffer_width, UINT back_buffer_height);

}  // namespace reflektortts
