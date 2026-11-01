#include <windows.h>

#include "api_client.h"
#include "crash_log.h"
#include "d3d11_renderer.h"
#include "d3d12_queue_hook.h"
#include "d3d12_renderer.h"
#include "d3d9_hook.h"
#include "d3d9_renderer.h"
#include "dll_load_watch.h"
#include "dxgi_hook.h"

namespace {

using namespace reflektortts;

void on_dxgi_present(IDXGISwapChain* swap_chain) {
    render_d3d11_frame(swap_chain);
    render_d3d12_frame(swap_chain);
}

// Where the system sends no DLL notifications, the overlay looks for new graphics DLLs this often.
constexpr DWORD kPollMs = 500;

bool is_loaded(const wchar_t* module_name) {
    return GetModuleHandleW(module_name) != nullptr;
}

// The core loads the overlay within seconds of the app starting; if the app has run longer,
// ReflektorTTS was started after it, and the app may already have made its graphics device.
constexpr ULONGLONG kJustStartedSeconds = 10;

bool app_just_started() {
    FILETIME created{}, exited{}, kernel{}, user{}, now{};
    GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user);
    GetSystemTimeAsFileTime(&now);
    auto ticks = [](FILETIME time) { return (ULONGLONG{time.dwHighDateTime} << 32) | time.dwLowDateTime; };
    return ticks(now) - ticks(created) < kJustStartedSeconds * 10'000'000;
}

// Hooks only the APIs whose DLLs the app has loaded, so the overlay never pulls in a graphics
// DLL (or a wrapper from the app folder) the app does not use. The core loads the overlay as
// soon as it sees the app's process, often before the app has set up its graphics, and apps
// may load another API later (after a launcher, or for a video), so each API is hooked when its
// DLL arrives, however late. Each is tried once.
DWORD WINAPI start_overlay(LPVOID) {
    install_crash_log();
    // A Direct3D 9 device may already exist only if its DLL was loaded before the overlay arrived
    // and the app was not just started.
    bool d3d9_device_may_exist = is_loaded(L"d3d9.dll") && !app_just_started();
    // Never closed: the loader keeps signalling it for as long as the app runs.
    HANDLE dll_loaded = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    bool notified = dll_loaded != nullptr && signal_on_dll_load(dll_loaded);

    bool tried_d3d12 = false, tried_dxgi = false, tried_d3d9 = false, client_started = false;
    while (!(tried_d3d12 && tried_dxgi && tried_d3d9)) {
        bool hooked = false;
        if (!tried_d3d12 && is_loaded(L"d3d12.dll")) {
            tried_d3d12 = true;
            install_d3d12_queue_hook();
        }
        if (!tried_dxgi && (is_loaded(L"d3d11.dll") || is_loaded(L"d3d12.dll"))) {
            tried_dxgi = true;
            hooked |= install_dxgi_hooks(on_dxgi_present);
        }
        if (!tried_d3d9 && is_loaded(L"d3d9.dll")) {
            tried_d3d9 = true;
            hooked |= install_d3d9_hooks(render_d3d9_frame, release_d3d9_device_objects, recreate_d3d9_device_objects,
                                         d3d9_device_may_exist);
        }
        if (hooked && !client_started) {
            client_started = true;
            start_api_client();
        }
        if (notified) {
            WaitForSingleObject(dll_loaded, INFINITE);
        } else {
            Sleep(kPollMs);
        }
    }
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
