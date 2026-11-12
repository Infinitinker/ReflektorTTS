// The overlay DLL's entry point, which the injector starts on a thread of its own in the app with the
// core's port: it installs the crash log, hooks each graphics API as soon as the app loads its DLL,
// and starts the API client once a hook is in place.

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <utility>

#include "api_client.h"
#include "diagnostics/crash_log.h"
#include "hooks/d3d12_queue_hook.h"
#include "hooks/d3d9_hook.h"
#include "hooks/dll_load_watch.h"
#include "hooks/dxgi_hook.h"
#include "renderers/d3d11_renderer.h"
#include "renderers/d3d12_renderer.h"
#include "renderers/d3d9_renderer.h"
#include "transport_winhttp.h"

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
    FILETIME created{};
    FILETIME exited{};
    FILETIME kernel{};
    FILETIME user{};
    FILETIME now{};
    GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user);
    GetSystemTimeAsFileTime(&now);
    auto ticks = [](FILETIME time) { return (ULONGLONG{time.dwHighDateTime} << 32) | time.dwLowDateTime; };
    return ticks(now) - ticks(created) < kJustStartedSeconds * 10'000'000;
}

// Hooks only the APIs whose DLLs the app has loaded, so the overlay never pulls in a Direct3D
// or DirectInput DLL (or a wrapper of one from the app folder) the app does not use; only
// dxgi.dll and d3dcompiler_47.dll, linked by ImGui's backends, always come with it. The core
// loads the overlay as soon as it sees the app's process, often before the app has set up its
// graphics, and apps may load another API later (after a launcher, or for a video), so each API
// is hooked when its DLL arrives, however late. Each is tried once.
DWORD run_overlay(int port) {
    install_crash_log();
    // A Direct3D 9 device may already exist only if its DLL was loaded before the overlay arrived
    // and the app was not just started.
    bool d3d9_device_may_exist = is_loaded(L"d3d9.dll") && !app_just_started();
    // Never closed: the loader keeps signaling it for as long as the app runs.
    HANDLE dll_loaded = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    bool notified = dll_loaded != nullptr && signal_on_dll_load(dll_loaded);

    bool tried_d3d12 = false;
    bool tried_dxgi = false;
    bool tried_d3d9 = false;
    bool client_started = false;
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
            if (std::unique_ptr<Transport> transport = make_winhttp_transport(L"ReflektorTTS overlay", port)) {
                start_api_client(std::move(transport));
            }
        }
        if (notified) {
            WaitForSingleObject(dll_loaded, INFINITE);
        } else {
            Sleep(kPollMs);
        }
    }
    return 0;
}

std::atomic_flag g_started;

}  // namespace

// The overlay's one export, which the injector runs on a thread of its own in the app once the DLL
// is loaded (reflektortts-inject.exe), rather than DllMain starting the overlay, so that it can pass
// the port of the core's API as the thread's parameter: 0 for the installed ReflektorTTS's. The DLL
// stays loaded while the app runs, so loading it again starts nothing more.
// NOLINTNEXTLINE(misc-use-internal-linkage)
extern "C" __declspec(dllexport) DWORD WINAPI reflektortts_start_overlay(LPVOID port) {
    if (g_started.test_and_set()) {
        return 0;
    }
    auto given = static_cast<int>(reinterpret_cast<std::intptr_t>(port));
    return run_overlay(given != 0 ? given : kDefaultCorePort);
}

// The loader finds the entry point by its name, so it keeps external linkage.
// NOLINTNEXTLINE(misc-use-internal-linkage)
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
