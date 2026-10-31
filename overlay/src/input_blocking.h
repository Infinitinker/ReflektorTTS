#pragma once

#include <windows.h>

namespace reflektortts {

// While the panel is open, the game must not see the keys and clicks meant for it. Starting to
// block hooks every keyboard and mouse API the game has loaded by then (DirectInput, window
// messages, key state, raw input, the cursor); later starts also hook APIs loaded since.
// Gamepads are not blocked: the panel is used with the mouse.
void block_game_input(bool blocked);

bool game_input_blocked();

// Whether a window message is input the game must not get while blocked. Key releases still
// reach it, so a key held when the panel opened is not stuck down after it closes.
bool is_blocked_message(UINT message);

}  // namespace reflektortts
