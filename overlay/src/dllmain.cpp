#include <windows.h>

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

bool is_loaded(const wchar_t* module_name) {
    return GetModuleHandleW(module_name) != nullptr;
}

// Hooks only the APIs whose DLLs the game has already loaded, so the overlay never pulls
// in a graphics DLL (or a wrapper from the game folder) the game does not use.
DWORD WINAPI start_overlay(LPVOID) {
    bool hooked = false;
    if (is_loaded(L"d3d12.dll")) {
        install_d3d12_queue_hook();
    }
    if (is_loaded(L"d3d11.dll") || is_loaded(L"d3d12.dll")) {
        hooked |= install_dxgi_hooks(on_dxgi_present);
    }
    if (is_loaded(L"d3d9.dll")) {
        hooked |= install_d3d9_hooks(render_d3d9_frame, release_d3d9_device_objects, recreate_d3d9_device_objects);
    }
    if (!hooked) {
        log_message("Overlay not started: the game uses none of Direct3D 9, 11 or 12");
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
