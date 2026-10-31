#include "dxgi_hook.h"

#include <d3d11.h>
#include <dxgi1_2.h>

#include <string>

#include "log.h"
#include "probe_window.h"
#include "vtable_hook.h"

namespace reflektortts {
namespace {

using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
using Present1Fn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain1*, UINT, UINT, const DXGI_PRESENT_PARAMETERS*);

constexpr int kPresentIndex = 8;
constexpr int kPresent1Index = 22;

SwapChainCallback g_on_present = nullptr;
PresentFn g_original_present = nullptr;
Present1Fn g_original_present1 = nullptr;

HRESULT STDMETHODCALLTYPE present_detour(IDXGISwapChain* swap_chain, UINT sync_interval, UINT flags) {
    g_on_present(swap_chain);
    return g_original_present(swap_chain, sync_interval, flags);
}

HRESULT STDMETHODCALLTYPE present1_detour(IDXGISwapChain1* swap_chain, UINT sync_interval, UINT flags,
                                          const DXGI_PRESENT_PARAMETERS* parameters) {
    g_on_present(swap_chain);
    return g_original_present1(swap_chain, sync_interval, flags, parameters);
}

// Prefers the d3d11.dll the game already uses (it may be a wrapper) over the system one.
// Direct3D 12 games may not load d3d11.dll, but their swap chains share the same vtable.
HMODULE d3d11_module() {
    HMODULE module = GetModuleHandleW(L"d3d11.dll");
    return module != nullptr ? module : LoadLibraryExW(L"d3d11.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
}

struct SwapChainVtable {
    void** entries = nullptr;
    // IDXGISwapChain1 extends IDXGISwapChain, so Present1 is in the same vtable when
    // the swap chain implements it (DXGI 1.2, Windows 8 and later).
    bool has_present1 = false;
};

// Swap chains share their class's vtable, so a throwaway swap chain gives us the game's.
bool find_swap_chain_vtable(SwapChainVtable& vtable) {
    HMODULE d3d11 = d3d11_module();
    auto create = d3d11 == nullptr ? nullptr
                                   : reinterpret_cast<decltype(&D3D11CreateDeviceAndSwapChain)>(
                                         GetProcAddress(d3d11, "D3D11CreateDeviceAndSwapChain"));
    if (create == nullptr) {
        log_message("d3d11.dll is not available");
        return false;
    }

    ProbeWindow window;
    DXGI_SWAP_CHAIN_DESC desc{};
    desc.BufferCount = 1;
    desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.OutputWindow = window.handle();
    desc.SampleDesc.Count = 1;
    desc.Windowed = TRUE;
    desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    IDXGISwapChain* swap_chain = nullptr;
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* context = nullptr;
    HRESULT result = create(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &desc,
                            &swap_chain, &device, nullptr, &context);
    if (FAILED(result)) {
        log_message("Could not create a probe D3D11 device (HRESULT " + std::to_string(result) + ")");
        return false;
    }
    vtable.entries = *reinterpret_cast<void***>(swap_chain);
    IDXGISwapChain1* swap_chain1 = nullptr;
    if (SUCCEEDED(swap_chain->QueryInterface(__uuidof(IDXGISwapChain1), reinterpret_cast<void**>(&swap_chain1)))) {
        vtable.has_present1 = *reinterpret_cast<void***>(swap_chain1) == vtable.entries;
        swap_chain1->Release();
    }
    swap_chain->Release();
    device->Release();
    context->Release();
    return true;
}

}  // namespace

bool install_dxgi_hooks(SwapChainCallback on_present) {
    SwapChainVtable vtable;
    if (!find_swap_chain_vtable(vtable)) {
        return false;
    }

    g_on_present = on_present;
    if (!hook_method(vtable.entries, kPresentIndex, &present_detour, &g_original_present) ||
        (vtable.has_present1 && !hook_method(vtable.entries, kPresent1Index, &present1_detour, &g_original_present1))) {
        log_message("Could not hook IDXGISwapChain methods");
        return false;
    }
    return true;
}

}  // namespace reflektortts
