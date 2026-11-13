// Turns blocking the app's input on and off with the panel, hooking the input APIs the app has
// loaded each time blocking starts.

#include "input/blocking.h"

#include <atomic>

#include "input/dinput_hook.h"
#include "input/win32_hook.h"

namespace reflektortts {
namespace {

std::atomic<bool> g_blocked = false;

}  // namespace

void block_app_input(bool blocked) {
    if (blocked) {
        install_win32_input_hooks();
        install_dinput_hooks();
    }
    g_blocked = blocked;
    on_win32_input_blocking(blocked);
}

bool app_input_blocked() {
    return g_blocked;
}

bool is_blocked_message(UINT message) {
    switch (message) {
        case WM_KEYDOWN:
        case WM_SYSKEYDOWN:
        case WM_CHAR:
        case WM_SYSCHAR:
        case WM_DEADCHAR:
        case WM_SYSDEADCHAR:
        case WM_UNICHAR:
        case WM_INPUT:
            return true;
        default:
            return message >= WM_MOUSEFIRST && message <= WM_MOUSELAST;
    }
}

}  // namespace reflektortts
