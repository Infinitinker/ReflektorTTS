#include "d3d9_hook.h"

#include <string>

#include "log.h"
#include "probe_window.h"
#include "vtable_hook.h"

namespace reflektortts {
namespace {

using ResetFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3DDevice9*, D3DPRESENT_PARAMETERS*);
using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3DDevice9*, const RECT*, const RECT*, HWND, const RGNDATA*);

constexpr int kResetIndex = 16;
constexpr int kPresentIndex = 17;

DeviceCallback g_on_present = nullptr;
DeviceCallback g_before_reset = nullptr;
DeviceCallback g_after_reset = nullptr;
ResetFn g_original_reset = nullptr;
PresentFn g_original_present = nullptr;

HRESULT STDMETHODCALLTYPE reset_detour(IDirect3DDevice9* device, D3DPRESENT_PARAMETERS* parameters) {
    g_before_reset(device);
    HRESULT result = g_original_reset(device, parameters);
    if (SUCCEEDED(result)) {
        g_after_reset(device);
    }
    return result;
}

HRESULT STDMETHODCALLTYPE present_detour(IDirect3DDevice9* device, const RECT* source, const RECT* destination,
                                         HWND window, const RGNDATA* dirty_region) {
    g_on_present(device);
    return g_original_present(device, source, destination, window, dirty_region);
}

// Devices share their class's vtable, so a throwaway device gives us the game's. It is a
// hardware (HAL) device like the ones games create.
void** find_device_vtable() {
    HMODULE d3d9 = GetModuleHandleW(L"d3d9.dll");
    auto create = d3d9 == nullptr
                      ? nullptr
                      : reinterpret_cast<decltype(&Direct3DCreate9)>(GetProcAddress(d3d9, "Direct3DCreate9"));
    if (create == nullptr) {
        log_message("d3d9.dll is not loaded");
        return nullptr;
    }
    IDirect3D9* direct3d = create(D3D_SDK_VERSION);
    if (direct3d == nullptr) {
        log_message("Could not create a probe Direct3D 9 object");
        return nullptr;
    }

    ProbeWindow window;
    D3DPRESENT_PARAMETERS parameters{};
    parameters.Windowed = TRUE;
    parameters.SwapEffect = D3DSWAPEFFECT_DISCARD;
    parameters.BackBufferFormat = D3DFMT_UNKNOWN;
    parameters.hDeviceWindow = window.handle();

    IDirect3DDevice9* device = nullptr;
    HRESULT result = direct3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, window.handle(),
                                            D3DCREATE_HARDWARE_VERTEXPROCESSING, &parameters, &device);
    void** vtable = nullptr;
    if (SUCCEEDED(result)) {
        vtable = *reinterpret_cast<void***>(device);
        device->Release();
    } else {
        log_message("Could not create a probe Direct3D 9 device (HRESULT " + std::to_string(result) + ")");
    }
    direct3d->Release();
    return vtable;
}

}  // namespace

bool install_d3d9_hooks(DeviceCallback on_present, DeviceCallback before_reset, DeviceCallback after_reset) {
    void** vtable = find_device_vtable();
    if (vtable == nullptr) {
        return false;
    }

    g_on_present = on_present;
    g_before_reset = before_reset;
    g_after_reset = after_reset;
    if (!hook_vtable_entry(vtable, kResetIndex, &reset_detour, &g_original_reset) ||
        !hook_vtable_entry(vtable, kPresentIndex, &present_detour, &g_original_present)) {
        log_message("Could not hook IDirect3DDevice9 methods");
        return false;
    }
    return true;
}

}  // namespace reflektortts
