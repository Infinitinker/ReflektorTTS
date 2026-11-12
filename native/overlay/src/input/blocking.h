// Blocking the app's keyboard and mouse input while the panel is open, so the keys and clicks
// meant for the panel do not reach the app.

#pragma once

#include <windows.h>

namespace reflektortts {

// While the panel is open, the app must not see the keys and clicks meant for it. Starting to
// block hooks every keyboard and mouse API the app has loaded by then (DirectInput, window
// messages, key state, raw input, the cursor); later starts also hook APIs loaded since.
// Gamepads are not blocked: the panel is used with the mouse.
void block_app_input(bool blocked);

bool app_input_blocked();

// Whether a window message is input the app must not get while blocked. Key releases still
// reach it, so a key held when the panel opened is not stuck down after it closes.
bool is_blocked_message(UINT message);

}  // namespace reflektortts
