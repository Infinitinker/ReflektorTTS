#include "input/panel_input.h"

#include <imgui.h>

#include <atomic>
#include <mutex>
#include <unordered_map>
#include <vector>

#include "input/blocking.h"

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

namespace reflektortts {
namespace {

std::atomic<bool> g_panel_open = false;
bool g_hotkey_down = false;

std::mutex g_windows_mutex;
std::unordered_map<HWND, WNDPROC> g_original_procs;

// Messages arrive on the app's message thread, which in many engines is not the one that
// draws; ImGui may only be used from the drawing thread, so they wait here until its next frame.
struct PanelMessage {
    HWND window;
    UINT message;
    WPARAM wparam;
    LPARAM lparam;
};
constexpr std::size_t kMaxWaitingMessages = 1024;  // If frames stop, older input is not worth keeping.
std::mutex g_messages_mutex;
std::vector<PanelMessage> g_waiting_messages;

void deliver_waiting_messages() {
    std::vector<PanelMessage> messages;
    {
        std::lock_guard lock(g_messages_mutex);
        messages.swap(g_waiting_messages);
    }
    for (const PanelMessage& m : messages) {
        ImGui_ImplWin32_WndProcHandler(m.window, m.message, m.wparam, m.lparam);
    }
}

bool is_down(int key) {
    return (GetAsyncKeyState(key) & 0x8000) != 0;
}

LRESULT CALLBACK overlay_window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    WNDPROC original = nullptr;
    {
        std::lock_guard lock(g_windows_mutex);
        original = g_original_procs[window];
    }
    // Input messages queued for the app are already taken off the queue by the message hooks;
    // this catches the ones sent straight to the window.
    if (g_panel_open) {
        send_to_panel(window, message, wparam, lparam);
        if (app_input_blocked() && is_blocked_message(message)) {
            return 0;
        }
    }
    return CallWindowProcW(original, window, message, wparam, lparam);
}

}  // namespace

void attach_input(HWND window) {
    std::lock_guard lock(g_windows_mutex);
    if (window == nullptr || g_original_procs.contains(window)) {
        return;
    }
    // Register the original first: the new procedure may run as soon as it is set.
    g_original_procs[window] = reinterpret_cast<WNDPROC>(GetWindowLongPtrW(window, GWLP_WNDPROC));
    SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(&overlay_window_proc));
}

// Apps using DirectInput, or replacing their window procedure, keep click messages from
// reaching ImGui; reading the buttons directly works regardless. ImGui ignores repeated
// states, so clicks that do arrive as messages are not counted twice.
void poll_mouse_buttons() {
    bool swapped = GetSystemMetrics(SM_SWAPBUTTON) != 0;
    ImGuiIO& io = ImGui::GetIO();
    io.AddMouseButtonEvent(ImGuiMouseButton_Left, is_down(swapped ? VK_RBUTTON : VK_LBUTTON));
    io.AddMouseButtonEvent(ImGuiMouseButton_Right, is_down(swapped ? VK_LBUTTON : VK_RBUTTON));
}

bool update_panel_toggle(HWND window) {
    bool foreground = GetForegroundWindow() == window;
    bool down = foreground && is_down(VK_CONTROL) && is_down(VK_SHIFT) && is_down('R');
    if (down && !g_hotkey_down) {
        g_panel_open = !g_panel_open;
        block_app_input(g_panel_open);
        ImGuiIO& io = ImGui::GetIO();
        // Apps often hide the system cursor, so ImGui draws its own while the panel is open.
        io.MouseDrawCursor = g_panel_open;
    }
    g_hotkey_down = down;
    deliver_waiting_messages();
    if (g_panel_open && foreground) {
        poll_mouse_buttons();
    }
    return g_panel_open;
}

bool panel_open() {
    return g_panel_open;
}

bool is_app_window(HWND window) {
    std::lock_guard lock(g_windows_mutex);
    return g_original_procs.contains(window);
}

// The panel is used with the mouse only: keys pressed for other overlays (or sent by them) while
// it is open would otherwise press its controls.
void send_to_panel(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (!g_panel_open || (message >= WM_KEYFIRST && message <= WM_KEYLAST)) {
        return;
    }
    std::lock_guard lock(g_messages_mutex);
    if (g_waiting_messages.size() < kMaxWaitingMessages) {
        g_waiting_messages.push_back({window, message, wparam, lparam});
    }
}

}  // namespace reflektortts
