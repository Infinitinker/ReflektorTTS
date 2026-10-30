#pragma once

namespace reflektortts {

// Hooks the Windows input functions games read: the message queue (GetMessage, PeekMessage),
// key state (GetAsyncKeyState, GetKeyState, GetKeyboardState), buffered raw input
// (GetRawInputBuffer) and the cursor (GetCursorPos, SetCursorPos, ClipCursor).
void install_win32_input_hooks();

// Frees the cursor the game may have trapped while input is blocked, and gives it back after.
void on_win32_input_blocking(bool blocked);

}  // namespace reflektortts
