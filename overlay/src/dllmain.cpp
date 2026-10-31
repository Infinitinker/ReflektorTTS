#include <windows.h>

#include "api_client.h"
#include "crash_log.h"
#include "d3d11_renderer.h"
#include "d3d12_queue_hook.h"
#include "d3d12_renderer.h"
#include "d3d9_hook.h"
#include "d3d9_renderer.h"
#include "dxgi_hook.h"
#include "log.h"

namespace {

using namespace reflektortts;

void on_dxgi_present(IDXGISwapChain* swap_chain) {
    render_d3d11_frame(swap_chain);
    render_d3d12_frame(swap_chain);
}

// The core loads the overlay as soon as it sees the game's process, often before the
// game has set up its graphics; wait for that instead of giving up.
constexpr DWORD kGraphicsPollMs = 500;
constexpr int kGraphicsPolls = 240;

bool is_loaded(const wchar_t* module_name) {
    return GetModuleHandleW(module_name) != nullptr;
}

bool graphics_loaded() {
    return is_loaded(L"d3d9.dll") || is_loaded(L"d3d11.dll") || is_loaded(L"d3d12.dll");
}

// The core loads the overlay within seconds of the game starting; if the game has run longer,
// ReflektorTTS was started after it, and the game may already have made its graphics device.
constexpr ULONGLONG kJustStartedSeconds = 10;

bool game_just_started() {
    FILETIME created{}, exited{}, kernel{}, user{}, now{};
    GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user);
    GetSystemTimeAsFileTime(&now);
    auto ticks = [](FILETIME time) { return (ULONGLONG{time.dwHighDateTime} << 32) | time.dwLowDateTime; };
    return ticks(now) - ticks(created) < kJustStartedSeconds * 10'000'000;
}

// Hooks only the APIs whose DLLs the game has loaded, so the overlay never pulls in a
// graphics DLL (or a wrapper from the game folder) the game does not use.
DWORD WINAPI start_overlay(LPVOID) {
    install_crash_log();
    bool just_started = game_just_started();
    for (int poll = 0; poll < kGraphicsPolls && !graphics_loaded(); ++poll) {
        Sleep(kGraphicsPollMs);
    }
    bool hooked = false;
    if (is_loaded(L"d3d12.dll")) {
        install_d3d12_queue_hook();
    }
    if (is_loaded(L"d3d11.dll") || is_loaded(L"d3d12.dll")) {
        hooked |= install_dxgi_hooks(on_dxgi_present);
    }
    if (is_loaded(L"d3d9.dll")) {
        hooked |= install_d3d9_hooks(render_d3d9_frame, release_d3d9_device_objects, recreate_d3d9_device_objects,
                                     !just_started);
    }
    if (!hooked) {
        log_message("Overlay not started: the game uses none of Direct3D 9, 11 or 12");
        return 0;
    }
    start_api_client();
    return 0;
}

}  // namespace

// The loader lock is held here, so hooking happens on a separate thread.
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        HANDLE thread = CreateThread(nullptr, 0, start_overlay, nullptr, 0, nullptr);
        if (thread != nullptr) {
            CloseHandle(thread);
        }
    }
    return TRUE;
}
