#pragma once

#include <windows.h>

namespace reflektortts {

// Routes the window's mouse and keyboard messages to ImGui while the panel is open, and keeps
// them from the game. Safe to call again for the same or a new window.
void attach_input(HWND window);

// Checks the Ctrl+Shift+R hotkey (only while the game window is in front), reads the
// mouse buttons while the panel is open, and returns whether the panel is open. Call once
// per frame, before ImGui::NewFrame.
bool update_panel_toggle(HWND window);

bool panel_open();

// Whether attach_input was called for the window: one the game draws to and the panel is shown on.
bool is_game_window(HWND window);

// Hands a window message to the panel (ImGui), e.g. one taken from the game's message queue.
void send_to_panel(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

}  // namespace reflektortts
