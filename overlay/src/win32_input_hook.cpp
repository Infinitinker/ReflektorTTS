#include "win32_input_hook.h"

#include <windows.h>

#include <cstdint>
#include <cstring>
#include <mutex>

#include "code_hook.h"
#include "input.h"
#include "input_blocking.h"
#include "log.h"

namespace reflektortts {
namespace {

// Each starts as the real function, so the overlay can call it even if hooking failed.
decltype(&GetMessageA) g_get_message_a = GetMessageA;
decltype(&GetMessageW) g_get_message_w = GetMessageW;
decltype(&PeekMessageA) g_peek_message_a = PeekMessageA;
decltype(&PeekMessageW) g_peek_message_w = PeekMessageW;
decltype(&GetAsyncKeyState) g_get_async_key_state = GetAsyncKeyState;
decltype(&GetKeyState) g_get_key_state = GetKeyState;
decltype(&GetKeyboardState) g_get_keyboard_state = GetKeyboardState;
decltype(&GetRawInputBuffer) g_get_raw_input_buffer = GetRawInputBuffer;
decltype(&GetCursorPos) g_get_cursor_pos = GetCursorPos;
decltype(&SetCursorPos) g_set_cursor_pos = SetCursorPos;
decltype(&ClipCursor) g_clip_cursor = ClipCursor;

std::mutex g_cursor_mutex;
POINT g_game_cursor{};      // Where the game last saw or put the cursor.
RECT g_game_clip{};         // The area the game last trapped the cursor in,
bool g_game_clips = false;  // if it did.

bool blocked_for_caller(const void* caller) {
    return game_input_blocked() && !is_overlay_code(caller);
}

// Input taken off the message queue for the game's window goes to the panel instead: the game
// gets WM_NULL. Other windows are left alone: DirectInput reads the keyboard through raw input sent to a
// hidden window of its own, and cutting that off would keep it from seeing keys released.
void filter_message(MSG* message, bool removed) {
    if (!removed || message == nullptr || !game_input_blocked() || !is_blocked_message(message->message) ||
        !is_game_window(message->hwnd)) {
        return;
    }
    send_to_panel(message->hwnd, message->message, message->wParam, message->lParam);
    message->message = WM_NULL;
}

BOOL WINAPI get_message_a(MSG* message, HWND window, UINT first, UINT last) {
    BOOL result = g_get_message_a(message, window, first, last);
    if (result > 0) {
        filter_message(message, true);
    }
    return result;
}

BOOL WINAPI get_message_w(MSG* message, HWND window, UINT first, UINT last) {
    BOOL result = g_get_message_w(message, window, first, last);
    if (result > 0) {
        filter_message(message, true);
    }
    return result;
}

BOOL WINAPI peek_message_a(MSG* message, HWND window, UINT first, UINT last, UINT remove) {
    BOOL result = g_peek_message_a(message, window, first, last, remove);
    if (result) {
        filter_message(message, (remove & PM_REMOVE) != 0);
    }
    return result;
}

BOOL WINAPI peek_message_w(MSG* message, HWND window, UINT first, UINT last, UINT remove) {
    BOOL result = g_peek_message_w(message, window, first, last, remove);
    if (result) {
        filter_message(message, (remove & PM_REMOVE) != 0);
    }
    return result;
}

// The real function still runs, so its "pressed since the last call" bit does not fire a
// stale key press at the game once blocking ends.
SHORT WINAPI get_async_key_state(int key) {
    SHORT state = g_get_async_key_state(key);
    return blocked_for_caller(__builtin_return_address(0)) ? 0 : state;
}

SHORT WINAPI get_key_state(int key) {
    SHORT state = g_get_key_state(key);
    return blocked_for_caller(__builtin_return_address(0)) ? 0 : state;
}

BOOL WINAPI get_keyboard_state(BYTE* keys) {
    BOOL result = g_get_keyboard_state(keys);
    if (result && keys != nullptr && blocked_for_caller(__builtin_return_address(0))) {
        std::memset(keys, 0, 256);
    }
    return result;
}

// NEXTRAWINPUTBLOCK, which MinGW's 64-bit headers cannot expand (they lack its QWORD). Blocks
// are aligned to a pointer's size: 8 bytes on 64-bit, 4 on 32-bit, as in the Windows SDK.
RAWINPUT* next_raw_input_block(RAWINPUT* input) {
    constexpr std::uintptr_t alignment = sizeof(void*);
    std::uintptr_t next = reinterpret_cast<std::uintptr_t>(input) + input->header.dwSize;
    return reinterpret_cast<RAWINPUT*>((next + alignment - 1) & ~(alignment - 1));
}

// Buffered raw input is read, so it does not pile up, then mouse and keyboard input is handed
// over as meant for another window: movement zeroed, keys released. Gamepads pass unchanged.
UINT WINAPI get_raw_input_buffer(RAWINPUT* data, UINT* size, UINT header_size) {
    UINT count = g_get_raw_input_buffer(data, size, header_size);
    if (count == static_cast<UINT>(-1) || data == nullptr || !game_input_blocked()) {
        return count;
    }
    RAWINPUT* input = data;
    for (UINT i = 0; i < count; ++i, input = next_raw_input_block(input)) {
        if (input->header.dwType == RIM_TYPEMOUSE) {
            input->header.hDevice = nullptr;
            input->header.wParam = RIM_INPUTSINK;
            std::memset(&input->data.mouse, 0, sizeof(input->data.mouse));
        } else if (input->header.dwType == RIM_TYPEKEYBOARD) {
            input->header.hDevice = nullptr;
            input->header.wParam = RIM_INPUTSINK;
            input->data.keyboard.Flags |= RI_KEY_BREAK;
            input->data.keyboard.VKey = 0;
        }
    }
    return count;
}

// While blocked, the game sees the cursor stay where it was, and cannot move or trap it.
BOOL WINAPI get_cursor_pos(POINT* point) {
    if (point != nullptr && blocked_for_caller(__builtin_return_address(0))) {
        std::lock_guard lock(g_cursor_mutex);
        *point = g_game_cursor;
        return TRUE;
    }
    return g_get_cursor_pos(point);
}

BOOL WINAPI set_cursor_pos(int x, int y) {
    if (blocked_for_caller(__builtin_return_address(0))) {
        std::lock_guard lock(g_cursor_mutex);
        g_game_cursor = {x, y};
        return TRUE;
    }
    return g_set_cursor_pos(x, y);
}

BOOL WINAPI clip_cursor(const RECT* area) {
    if (!is_overlay_code(__builtin_return_address(0))) {
        std::lock_guard lock(g_cursor_mutex);
        g_game_clips = area != nullptr;
        if (area != nullptr) {
            g_game_clip = *area;
        }
    }
    return g_clip_cursor(game_input_blocked() ? nullptr : area);
}

}  // namespace

void install_win32_input_hooks() {
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    bool hooked = hook_export(user32, "GetMessageA", &get_message_a, &g_get_message_a) &
                  hook_export(user32, "GetMessageW", &get_message_w, &g_get_message_w) &
                  hook_export(user32, "PeekMessageA", &peek_message_a, &g_peek_message_a) &
                  hook_export(user32, "PeekMessageW", &peek_message_w, &g_peek_message_w) &
                  hook_export(user32, "GetAsyncKeyState", &get_async_key_state, &g_get_async_key_state) &
                  hook_export(user32, "GetKeyState", &get_key_state, &g_get_key_state) &
                  hook_export(user32, "GetKeyboardState", &get_keyboard_state, &g_get_keyboard_state) &
                  hook_export(user32, "GetRawInputBuffer", &get_raw_input_buffer, &g_get_raw_input_buffer) &
                  hook_export(user32, "GetCursorPos", &get_cursor_pos, &g_get_cursor_pos) &
                  hook_export(user32, "SetCursorPos", &set_cursor_pos, &g_set_cursor_pos) &
                  hook_export(user32, "ClipCursor", &clip_cursor, &g_clip_cursor);
    if (!hooked) {
        log_message("Some Windows input functions could not be hooked; the game may still get some input");
    }
}

void on_win32_input_blocking(bool blocked) {
    std::lock_guard lock(g_cursor_mutex);
    if (blocked) {
        g_get_cursor_pos(&g_game_cursor);
        g_clip_cursor(nullptr);
        return;
    }
    // Back where the game left it, so a game that keeps the cursor centered does not see a jump.
    g_set_cursor_pos(g_game_cursor.x, g_game_cursor.y);
    if (g_game_clips) {
        g_clip_cursor(&g_game_clip);
    }
}

}  // namespace reflektortts
