#pragma once

#include <windows.h>

namespace reflektortts {

// Routes the window's mouse and keyboard messages to ImGui while the panel is open.
// Safe to call again for the same or a new window.
void attach_input(HWND window);

// Checks the Ctrl+Shift+R hotkey (only while the game window is in front), reads the
// mouse buttons while the panel is open, and returns whether the panel is open. Call once
// per frame, before ImGui::NewFrame.
bool update_panel_toggle(HWND window);

bool panel_open();

}  // namespace reflektortts
