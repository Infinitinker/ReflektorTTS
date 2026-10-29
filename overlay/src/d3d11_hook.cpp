#include "d3d11_hook.h"

#include <MinHook.h>
#include <d3d11.h>

#include "log.h"

namespace reflektortts {
namespace {

using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
using ResizeBuffersFn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT, UINT, DXGI_FORMAT, UINT);

constexpr int kPresentIndex = 8;
constexpr int kResizeBuffersIndex = 13;

SwapChainCallback g_on_present = nullptr;
SwapChainCallback g_before_resize = nullptr;
PresentFn g_original_present = nullptr;
ResizeBuffersFn g_original_resize_buffers = nullptr;

HRESULT STDMETHODCALLTYPE present_detour(IDXGISwapChain* swap_chain, UINT sync_interval, UINT flags) {
    g_on_present(swap_chain);
    return g_original_present(swap_chain, sync_interval, flags);
}

HRESULT STDMETHODCALLTYPE resize_buffers_detour(IDXGISwapChain* swap_chain, UINT buffer_count, UINT width,
                                                UINT height, DXGI_FORMAT format, UINT flags) {
    g_before_resize(swap_chain);
    return g_original_resize_buffers(swap_chain, buffer_count, width, height, format, flags);
}

// Every swap chain shares one vtable, so a throwaway one tells us where the methods are.
bool find_swap_chain_methods(void*& present, void*& resize_buffers) {
    WNDCLASSEXW window_class{};
    window_class.cbSize = sizeof(window_class);
    window_class.lpfnWndProc = DefWindowProcW;
    window_class.hInstance = GetModuleHandleW(nullptr);
    window_class.lpszClassName = L"ReflektorTTSProbe";
    RegisterClassExW(&window_class);
    HWND window = CreateWindowExW(0, window_class.lpszClassName, L"", WS_OVERLAPPEDWINDOW, 0, 0, 100, 100,
                                  nullptr, nullptr, window_class.hInstance, nullptr);

    DXGI_SWAP_CHAIN_DESC desc{};
    desc.BufferCount = 1;
    desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.OutputWindow = window;
    desc.SampleDesc.Count = 1;
    desc.Windowed = TRUE;
    desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    IDXGISwapChain* swap_chain = nullptr;
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* context = nullptr;
    HRESULT result = D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0,
                                                   D3D11_SDK_VERSION, &desc, &swap_chain, &device, nullptr,
                                                   &context);
    bool found = SUCCEEDED(result);
    if (found) {
        void** vtable = *reinterpret_cast<void***>(swap_chain);
        present = vtable[kPresentIndex];
        resize_buffers = vtable[kResizeBuffersIndex];
        swap_chain->Release();
        device->Release();
        context->Release();
    } else {
        log_message("Could not create a probe D3D11 device (HRESULT " + std::to_string(result) + ")");
    }

    DestroyWindow(window);
    UnregisterClassW(window_class.lpszClassName, window_class.hInstance);
    return found;
}

}  // namespace

bool install_d3d11_hooks(SwapChainCallback on_present, SwapChainCallback before_resize) {
    void* present = nullptr;
    void* resize_buffers = nullptr;
    if (!find_swap_chain_methods(present, resize_buffers)) {
        return false;
    }

    g_on_present = on_present;
    g_before_resize = before_resize;

    if (MH_Initialize() != MH_OK) {
        log_message("MinHook failed to initialize");
        return false;
    }
    if (MH_CreateHook(present, reinterpret_cast<void*>(&present_detour),
                      reinterpret_cast<void**>(&g_original_present)) != MH_OK ||
        MH_CreateHook(resize_buffers, reinterpret_cast<void*>(&resize_buffers_detour),
                      reinterpret_cast<void**>(&g_original_resize_buffers)) != MH_OK ||
        MH_EnableHook(MH_ALL_HOOKS) != MH_OK) {
        log_message("Could not hook IDXGISwapChain methods");
        return false;
    }
    return true;
}

}  // namespace reflektortts
