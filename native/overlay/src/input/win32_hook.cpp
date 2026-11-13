// Hooks the message queue, key state, raw input and cursor functions: while input is blocked, the
// app's input messages go to the panel, it reads no keys pressed and no mouse movement, and it can
// neither move nor trap the cursor. The overlay's own calls are let through.

#include "input/win32_hook.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <mutex>

#include "hooks/code_hook.h"
#include "input/blocking.h"
#include "input/panel_input.h"
#include "log.h"
#include "memory/addresses.h"

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
POINT g_app_cursor{};      // Where the app last saw or put the cursor.
RECT g_app_clip{};         // The area the app last trapped the cursor in,
bool g_app_clips = false;  // if it did.

bool blocked_for_caller(const void* caller) {
    return app_input_blocked() && !is_overlay_code(caller);
}

// Input taken off the message queue for the app's window goes to the panel instead: the app
// gets WM_NULL. Other windows are left alone: DirectInput reads the keyboard through raw input sent to a
// hidden window of its own, and cutting that off would keep it from seeing keys released.
void filter_message(MSG* message, bool removed) {
    if (!removed || message == nullptr || !app_input_blocked() || !is_blocked_message(message->message) ||
        !is_app_window(message->hwnd)) {
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
// stale key press at the app once blocking ends.
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

// RAWINPUTHEADER as 64-bit Windows lays it out. A 32-bit app on 64-bit Windows (WOW64) gets
// GetRawInputBuffer's blocks in this layout, 8-byte aligned, not in its own 32-bit one.
struct RawInputHeader64 {
    DWORD dwType;
    DWORD dwSize;
    std::uint64_t hDevice;
    std::uint64_t wParam;
};
static_assert(sizeof(RawInputHeader64) == 24, "RAWINPUTHEADER is 24 bytes on 64-bit Windows");

bool runs_on_wow64() {
    static const bool wow64 = [] {
        BOOL result = FALSE;
        return IsWow64Process(GetCurrentProcess(), &result) && result;
    }();
    return wow64;
}

// Hands each mouse and keyboard block over as meant for another window: movement zeroed, keys
// released. Gamepads pass unchanged. Blocks follow each other at alignment, as NEXTRAWINPUTBLOCK
// steps (which MinGW's 64-bit headers cannot expand, lacking its QWORD); a block's data follows
// its header, and the mouse and keyboard data is laid out the same in 32 and 64 bits.
template <typename Header>
void hand_over_raw_input(BYTE* blocks, UINT count, std::uintptr_t alignment) {
    BYTE* block = blocks;
    for (UINT i = 0; i < count; ++i) {
        auto* header = object_at<Header>(block);
        BYTE* payload = pointer_at<BYTE>(address_of(block) + sizeof(Header));
        if (header->dwType == RIM_TYPEMOUSE) {
            header->hDevice = {};
            header->wParam = RIM_INPUTSINK;
            std::memset(payload, 0, sizeof(RAWMOUSE));
        } else if (header->dwType == RIM_TYPEKEYBOARD) {
            header->hDevice = {};
            header->wParam = RIM_INPUTSINK;
            auto* keyboard = object_at<RAWKEYBOARD>(payload);
            keyboard->Flags |= RI_KEY_BREAK;
            keyboard->VKey = 0;
        }
        std::uintptr_t next = address_of(block) + header->dwSize;
        block = pointer_at<BYTE>((next + alignment - 1) & ~(alignment - 1));
    }
}

// What GetRawInputBuffer returns when it fails.
constexpr UINT kRawInputError = static_cast<UINT>(-1);

// Buffered raw input is read, so it does not pile up, then handed over as meant for another
// window (see hand_over_raw_input).
UINT WINAPI get_raw_input_buffer(RAWINPUT* data, UINT* size, UINT header_size) {
    UINT count = g_get_raw_input_buffer(data, size, header_size);
    if (count == kRawInputError || data == nullptr || !app_input_blocked()) {
        return count;
    }
    BYTE* blocks = bytes_of(data);
    if (sizeof(void*) == 4 && runs_on_wow64()) {
        hand_over_raw_input<RawInputHeader64>(blocks, count, 8);
    } else {
        hand_over_raw_input<RAWINPUTHEADER>(blocks, count, sizeof(void*));
    }
    return count;
}

// While blocked, the app sees the cursor stay where it was, and cannot move or trap it.
BOOL WINAPI get_cursor_pos(POINT* point) {
    if (point != nullptr && blocked_for_caller(__builtin_return_address(0))) {
        std::scoped_lock lock(g_cursor_mutex);
        *point = g_app_cursor;
        return TRUE;
    }
    return g_get_cursor_pos(point);
}

BOOL WINAPI set_cursor_pos(int x, int y) {
    if (blocked_for_caller(__builtin_return_address(0))) {
        std::scoped_lock lock(g_cursor_mutex);
        g_app_cursor = {.x = x, .y = y};
        return TRUE;
    }
    return g_set_cursor_pos(x, y);
}

BOOL WINAPI clip_cursor(const RECT* area) {
    if (!is_overlay_code(__builtin_return_address(0))) {
        std::scoped_lock lock(g_cursor_mutex);
        g_app_clips = area != nullptr;
        if (area != nullptr) {
            g_app_clip = *area;
        }
    }
    return g_clip_cursor(app_input_blocked() ? nullptr : area);
}

}  // namespace

void install_win32_input_hooks() {
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    // Each is hooked, in order, whether those before it were or not.
    const std::array hooked{hook_export(user32, "GetMessageA", &get_message_a, &g_get_message_a),
                            hook_export(user32, "GetMessageW", &get_message_w, &g_get_message_w),
                            hook_export(user32, "PeekMessageA", &peek_message_a, &g_peek_message_a),
                            hook_export(user32, "PeekMessageW", &peek_message_w, &g_peek_message_w),
                            hook_export(user32, "GetAsyncKeyState", &get_async_key_state, &g_get_async_key_state),
                            hook_export(user32, "GetKeyState", &get_key_state, &g_get_key_state),
                            hook_export(user32, "GetKeyboardState", &get_keyboard_state, &g_get_keyboard_state),
                            hook_export(user32, "GetRawInputBuffer", &get_raw_input_buffer, &g_get_raw_input_buffer),
                            hook_export(user32, "GetCursorPos", &get_cursor_pos, &g_get_cursor_pos),
                            hook_export(user32, "SetCursorPos", &set_cursor_pos, &g_set_cursor_pos),
                            hook_export(user32, "ClipCursor", &clip_cursor, &g_clip_cursor)};
    if (std::ranges::find(hooked, false) != hooked.end()) {
        log_message("Some Windows input functions could not be hooked; the app may still get some input");
    }
}

void on_win32_input_blocking(bool blocked) {
    std::scoped_lock lock(g_cursor_mutex);
    if (blocked) {
        g_get_cursor_pos(&g_app_cursor);
        g_clip_cursor(nullptr);
        return;
    }
    // Back where the app left it, so an app that keeps the cursor centered does not see a jump.
    g_set_cursor_pos(g_app_cursor.x, g_app_cursor.y);
    if (g_app_clips) {
        g_clip_cursor(&g_app_clip);
    }
}

}  // namespace reflektortts
