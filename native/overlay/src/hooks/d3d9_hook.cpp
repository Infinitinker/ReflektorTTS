// Hooks IDirect3DDevice9::Present and Reset: on devices as the app creates them, through
// IDirect3D9::CreateDevice and CreateDeviceEx, and on a device made before the overlay arrived,
// through the vtable of a throwaway probe device.

#include "hooks/d3d9_hook.h"

#include <array>
#include <cstddef>
#include <mutex>
#include <string>
#include <utility>

#include "hooks/probe_window.h"
#include "hooks/vtable_hook.h"
#include "log.h"

namespace reflektortts {
namespace {

using ResetFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3DDevice9*, D3DPRESENT_PARAMETERS*);
using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3DDevice9*, const RECT*, const RECT*, HWND, const RGNDATA*);
using CreateDeviceFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3D9*, UINT, D3DDEVTYPE, HWND, DWORD, D3DPRESENT_PARAMETERS*,
                                                   IDirect3DDevice9**);
using CreateDeviceExFn = HRESULT(STDMETHODCALLTYPE*)(IDirect3D9Ex*, UINT, D3DDEVTYPE, HWND, DWORD,
                                                     D3DPRESENT_PARAMETERS*, D3DDISPLAYMODEEX*, IDirect3DDevice9Ex**);

constexpr int kCreateDeviceIndex = 16;    // IDirect3D9
constexpr int kCreateDeviceExIndex = 20;  // IDirect3D9Ex
constexpr int kResetIndex = 16;           // IDirect3DDevice9
constexpr int kPresentIndex = 17;

DeviceCallback g_on_present = nullptr;
DeviceCallback g_before_reset = nullptr;
DeviceCallback g_after_reset = nullptr;
std::mutex g_mutex;

// Each hooked class (vtable) keeps its own originals, reached by its own copy of the detours:
// a code hook sends objects of any class sharing the method through the copy that installed it.
// Device classes differ e.g. between "pure" devices and ordinary ones.
struct DeviceClass {
    void** vtable = nullptr;
    ResetFn reset = nullptr;
    PresentFn present = nullptr;
};
constexpr int kMaxDeviceClasses = 4;
DeviceClass g_devices[kMaxDeviceClasses];
int g_device_count = 0;

template <int N>
HRESULT STDMETHODCALLTYPE reset_detour(IDirect3DDevice9* device, D3DPRESENT_PARAMETERS* parameters) {
    g_before_reset(device);
    HRESULT result = g_devices[N].reset(device, parameters);
    if (SUCCEEDED(result)) {
        g_after_reset(device);
    }
    return result;
}

template <int N>
HRESULT STDMETHODCALLTYPE present_detour(IDirect3DDevice9* device, const RECT* source, const RECT* destination,
                                         HWND window, const RGNDATA* dirty_region) {
    g_on_present(device);
    return g_devices[N].present(device, source, destination, window, dirty_region);
}

template <std::size_t... N>
constexpr auto make_device_detours(std::index_sequence<N...>) {
    return std::pair{std::array<ResetFn, kMaxDeviceClasses>{&reset_detour<N>...},
                     std::array<PresentFn, kMaxDeviceClasses>{&present_detour<N>...}};
}
constexpr auto kDeviceDetours = make_device_detours(std::make_index_sequence<kMaxDeviceClasses>());

bool hook_device_class(void** vtable) {
    std::lock_guard lock(g_mutex);
    for (int i = 0; i < g_device_count; ++i) {
        if (g_devices[i].vtable == vtable) {
            return true;
        }
    }
    if (g_device_count == kMaxDeviceClasses) {
        log_message("Too many Direct3D 9 device classes to hook");
        return false;
    }
    int n = g_device_count++;
    DeviceClass& hooked = g_devices[n];
    hooked.vtable = vtable;
    bool ok = hook_method(vtable, kResetIndex, kDeviceDetours.first[n], &hooked.reset) &&
              hook_method(vtable, kPresentIndex, kDeviceDetours.second[n], &hooked.present);
    if (!ok) {
        log_message("Could not hook IDirect3DDevice9 methods");
    }
    return ok;
}

// The Direct3D objects devices are made from: IDirect3D9, and IDirect3D9Ex if its class differs.
struct FactoryClass {
    void** vtable = nullptr;
    CreateDeviceFn create_device = nullptr;
};
constexpr int kMaxFactoryClasses = 2;
FactoryClass g_factories[kMaxFactoryClasses];
int g_factory_count = 0;
CreateDeviceExFn g_original_create_device_ex = nullptr;

void hook_new_device(HRESULT result, void* device) {
    if (SUCCEEDED(result) && device != nullptr && hook_device_class(*static_cast<void***>(device))) {
        log_message("Hooked the app's Direct3D 9 device as it was created");
    }
}

template <int N>
HRESULT STDMETHODCALLTYPE create_device_detour(IDirect3D9* direct3d, UINT adapter, D3DDEVTYPE type, HWND window,
                                               DWORD flags, D3DPRESENT_PARAMETERS* parameters,
                                               IDirect3DDevice9** device) {
    HRESULT result = g_factories[N].create_device(direct3d, adapter, type, window, flags, parameters, device);
    hook_new_device(result, device != nullptr ? *device : nullptr);
    return result;
}

HRESULT STDMETHODCALLTYPE create_device_ex_detour(IDirect3D9Ex* direct3d, UINT adapter, D3DDEVTYPE type, HWND window,
                                                  DWORD flags, D3DPRESENT_PARAMETERS* parameters,
                                                  D3DDISPLAYMODEEX* mode, IDirect3DDevice9Ex** device) {
    HRESULT result = g_original_create_device_ex(direct3d, adapter, type, window, flags, parameters, mode, device);
    hook_new_device(result, device != nullptr ? *device : nullptr);
    return result;
}

constexpr std::array<CreateDeviceFn, kMaxFactoryClasses> kFactoryDetours{&create_device_detour<0>,
                                                                         &create_device_detour<1>};

bool hook_factory_class(void** vtable, bool is_ex) {
    std::lock_guard lock(g_mutex);
    int n = 0;
    while (n < g_factory_count && g_factories[n].vtable != vtable) {
        ++n;
    }
    if (n == g_factory_count) {
        if (n == kMaxFactoryClasses) {
            return false;
        }
        g_factories[n].vtable = vtable;
        ++g_factory_count;
        if (!hook_method(vtable, kCreateDeviceIndex, kFactoryDetours[n], &g_factories[n].create_device)) {
            return false;
        }
    }
    return !is_ex || hook_method(vtable, kCreateDeviceExIndex, &create_device_ex_detour, &g_original_create_device_ex);
}

// Making a Direct3D object needs no window or device, so it is safe whatever state the app is in.
bool hook_device_creation(HMODULE d3d9) {
    bool hooked = false;
    auto create = reinterpret_cast<decltype(&Direct3DCreate9)>(GetProcAddress(d3d9, "Direct3DCreate9"));
    if (IDirect3D9* direct3d = create != nullptr ? create(D3D_SDK_VERSION) : nullptr) {
        hooked = hook_factory_class(*reinterpret_cast<void***>(direct3d), false);
        direct3d->Release();
    }
    auto create_ex = reinterpret_cast<decltype(&Direct3DCreate9Ex)>(GetProcAddress(d3d9, "Direct3DCreate9Ex"));
    IDirect3D9Ex* direct3d_ex = nullptr;
    if (create_ex != nullptr && SUCCEEDED(create_ex(D3D_SDK_VERSION, &direct3d_ex))) {
        hooked = hook_factory_class(*reinterpret_cast<void***>(direct3d_ex), true) && hooked;
        direct3d_ex->Release();
    }
    if (!hooked) {
        log_message("Could not hook Direct3D 9 device creation");
    }
    return hooked;
}

// Devices share their class's vtable, so a throwaway device gives us the class of a device the
// app made before the overlay arrived. A hardware (HAL) device is like the ones apps create;
// while an app owns the screen in fullscreen that fails, but a null-reference device does not.
void** probe_device_vtable(HMODULE d3d9) {
    auto create = reinterpret_cast<decltype(&Direct3DCreate9)>(GetProcAddress(d3d9, "Direct3DCreate9"));
    IDirect3D9* direct3d = create != nullptr ? create(D3D_SDK_VERSION) : nullptr;
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

    void** vtable = nullptr;
    for (auto [type, flags] : {std::pair{D3DDEVTYPE_HAL, DWORD{D3DCREATE_HARDWARE_VERTEXPROCESSING}},
                               std::pair{D3DDEVTYPE_NULLREF, DWORD{D3DCREATE_SOFTWARE_VERTEXPROCESSING}}}) {
        IDirect3DDevice9* device = nullptr;
        HRESULT result = direct3d->CreateDevice(D3DADAPTER_DEFAULT, type, window.handle(), flags, &parameters, &device);
        if (SUCCEEDED(result)) {
            vtable = *reinterpret_cast<void***>(device);
            device->Release();
            break;
        }
        log_message("Could not create a probe Direct3D 9 device of type " + std::to_string(type) + " (HRESULT " +
                    std::to_string(result) + ")");
    }
    direct3d->Release();
    return vtable;
}

}  // namespace

bool install_d3d9_hooks(DeviceCallback on_present, DeviceCallback before_reset, DeviceCallback after_reset,
                        bool device_may_exist) {
    HMODULE d3d9 = GetModuleHandleW(L"d3d9.dll");
    if (d3d9 == nullptr) {
        log_message("d3d9.dll is not loaded");
        return false;
    }
    g_on_present = on_present;
    g_before_reset = before_reset;
    g_after_reset = after_reset;
    bool hooked = hook_device_creation(d3d9);
    if (device_may_exist) {
        void** vtable = probe_device_vtable(d3d9);
        hooked = (vtable != nullptr && hook_device_class(vtable)) || hooked;
    }
    return hooked;
}

}  // namespace reflektortts
