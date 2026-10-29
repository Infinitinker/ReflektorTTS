#include <windows.h>

#include "d3d11_hook.h"
#include "imgui_renderer.h"
#include "log.h"

namespace {

DWORD WINAPI start_overlay(LPVOID) {
    if (!reflektortts::install_d3d11_hooks(reflektortts::render_overlay_frame,
                                           reflektortts::release_overlay_render_target)) {
        reflektortts::log_message("Overlay not started: Direct3D 11 hooks could not be installed");
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
