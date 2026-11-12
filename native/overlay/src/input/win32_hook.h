// Hooks on the Windows input functions apps read, which keep keys, clicks and the cursor from the
// app while its input is blocked.

#pragma once

namespace reflektortts {

// Hooks the Windows input functions apps read: the message queue (GetMessage, PeekMessage),
// key state (GetAsyncKeyState, GetKeyState, GetKeyboardState), buffered raw input
// (GetRawInputBuffer) and the cursor (GetCursorPos, SetCursorPos, ClipCursor).
void install_win32_input_hooks();

// Frees the cursor the app may have trapped while input is blocked, and gives it back after.
void on_win32_input_blocking(bool blocked);

}  // namespace reflektortts
