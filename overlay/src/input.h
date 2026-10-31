#pragma once

#include <windows.h>

namespace reflektortts {

// Routes the window's mouse messages to ImGui while the panel is open, and keeps mouse and
// keyboard messages from the game. Safe to call again for the same or a new window.
void attach_input(HWND window);

// Checks the Ctrl+Shift+R hotkey (only while the game window is in front), hands the panel the
// window messages sent to it since the last frame, reads the mouse buttons while the panel is
// open, and returns whether the panel is open. Call once per frame, before ImGui::NewFrame, on
// the thread that draws.
bool update_panel_toggle(HWND window);

bool panel_open();

// Whether attach_input was called for the window: one the game draws to and the panel is shown on.
bool is_game_window(HWND window);

// Hands a window message to the panel (ImGui), e.g. one taken from the game's message queue;
// keyboard messages are dropped, since the panel is used with the mouse only. Safe from any
// thread: the panel receives it at the start of its next frame.
void send_to_panel(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

}  // namespace reflektortts
