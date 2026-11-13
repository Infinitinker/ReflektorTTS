// Sets up ImGui on the app's Direct3D 11 device and draws each frame on the swap chain's back
// buffer, following the swap chain and device the app presented with last.

#include "renderers/d3d11_renderer.h"

#include <d3d11.h>
#include <imgui.h>
#include <imgui_impl_dx11.h>

#include "log.h"
#include "renderers/overlay_frame.h"

namespace reflektortts {
namespace {

enum class State { NotStarted, Running, Disabled };

State g_state = State::NotStarted;
IDXGISwapChain* g_swap_chain = nullptr;
ID3D11Device* g_device = nullptr;
ID3D11DeviceContext* g_context = nullptr;

// A replaced device is abandoned, never released (see forget_renderer_backend).
bool use_device(ID3D11Device* device) {
    if (device == g_device) {
        device->Release();
        return true;
    }
    if (g_device != nullptr) {
        forget_renderer_backend();
    }
    g_device = device;
    g_device->GetImmediateContext(&g_context);
    return ImGui_ImplDX11_Init(g_device, g_context);
}

// Whether the swap chain belongs to the device the overlay draws with. A swap chain the app
// recreates, with a new device, can get the address of the one it freed, so the address alone
// does not tell.
bool on_our_device(IDXGISwapChain* swap_chain) {
    ID3D11Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(IID_PPV_ARGS(&device)))) {
        return false;
    }
    device->Release();
    return device == g_device;
}

// Apps replace their swap chain, and sometimes their device, e.g. when switching from
// the menu to gameplay, so the overlay follows the swap chain that presented last.
void attach(IDXGISwapChain* swap_chain) {
    ID3D11Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(IID_PPV_ARGS(&device)))) {
        return;
    }
    DXGI_SWAP_CHAIN_DESC desc{};
    swap_chain->GetDesc(&desc);
    if (g_state == State::NotStarted && !claim_overlay("Direct3D 11", desc.OutputWindow)) {
        device->Release();
        g_state = State::Disabled;
        return;
    }
    set_overlay_window(desc.OutputWindow);
    if (!use_device(device)) {
        log_message("ImGui Direct3D 11 backend failed to initialize; overlay disabled");
        g_state = State::Disabled;
        return;
    }
    g_swap_chain = swap_chain;
    g_state = State::Running;
}

// ImGui's backend saves and restores the state it changes, except that it unbinds the hull,
// domain and compute shaders and leaves them unbound. Apps that keep those bound between
// frames (tessellation, compute) would then draw without them and crash in the driver.
template <typename Shader>
struct ShaderBinding {
    Shader* shader = nullptr;
    ID3D11ClassInstance* instances[D3D11_SHADER_MAX_INTERFACES] = {};
    UINT instance_count = D3D11_SHADER_MAX_INTERFACES;

    void release() {
        if (shader != nullptr) {
            shader->Release();
        }
        for (UINT i = 0; i < instance_count; ++i) {
            if (instances[i] != nullptr) {
                instances[i]->Release();
            }
        }
    }
};

struct ShaderStages {
    ShaderBinding<ID3D11HullShader> hull;
    ShaderBinding<ID3D11DomainShader> domain;
    ShaderBinding<ID3D11ComputeShader> compute;

    explicit ShaderStages(ID3D11DeviceContext* context) {
        context->HSGetShader(&hull.shader, hull.instances, &hull.instance_count);
        context->DSGetShader(&domain.shader, domain.instances, &domain.instance_count);
        context->CSGetShader(&compute.shader, compute.instances, &compute.instance_count);
    }

    void restore(ID3D11DeviceContext* context) {
        context->HSSetShader(hull.shader, hull.instances, hull.instance_count);
        context->DSSetShader(domain.shader, domain.instances, domain.instance_count);
        context->CSSetShader(compute.shader, compute.instances, compute.instance_count);
        hull.release();
        domain.release();
        compute.release();
    }
};

ID3D11RenderTargetView* create_render_target(IDXGISwapChain* swap_chain, D3D11_TEXTURE2D_DESC& desc) {
    ID3D11Texture2D* back_buffer = nullptr;
    if (FAILED(swap_chain->GetBuffer(0, IID_PPV_ARGS(&back_buffer)))) {
        return nullptr;
    }
    back_buffer->GetDesc(&desc);
    ID3D11RenderTargetView* target = nullptr;
    g_device->CreateRenderTargetView(back_buffer, nullptr, &target);
    back_buffer->Release();
    return target;
}

}  // namespace

void render_d3d11_frame(IDXGISwapChain* swap_chain) {
    if (g_state != State::Disabled && (swap_chain != g_swap_chain || !on_our_device(swap_chain))) {
        attach(swap_chain);
    }
    if (g_state != State::Running || swap_chain != g_swap_chain) {
        return;
    }
    // The view is created per frame so the overlay never keeps the app's back buffer alive.
    D3D11_TEXTURE2D_DESC desc{};
    ID3D11RenderTargetView* target = create_render_target(swap_chain, desc);
    if (target == nullptr) {
        return;
    }

    ImGui_ImplDX11_NewFrame();
    build_overlay_frame(desc.Width, desc.Height);

    // Setting one render target unbinds the others, so all of the app's are put back.
    ID3D11RenderTargetView* app_targets[D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT] = {};
    ID3D11DepthStencilView* app_depth = nullptr;
    g_context->OMGetRenderTargets(D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT, app_targets, &app_depth);
    ShaderStages app_stages(g_context);
    g_context->OMSetRenderTargets(1, &target, nullptr);
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
    app_stages.restore(g_context);
    g_context->OMSetRenderTargets(D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT, app_targets, app_depth);
    for (ID3D11RenderTargetView* app_target : app_targets) {
        if (app_target != nullptr) {
            app_target->Release();
        }
    }
    if (app_depth != nullptr) {
        app_depth->Release();
    }
    target->Release();
}

}  // namespace reflektortts
