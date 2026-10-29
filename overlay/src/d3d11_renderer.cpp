#include "d3d11_renderer.h"

#include <d3d11.h>
#include <imgui.h>
#include <imgui_impl_dx11.h>

#include "log.h"
#include "overlay_frame.h"

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

// Games replace their swap chain, and sometimes their device, e.g. when switching from
// the menu to gameplay, so the overlay follows the swap chain that presented last.
void attach(IDXGISwapChain* swap_chain) {
    ID3D11Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&device)))) {
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

ID3D11RenderTargetView* create_render_target(IDXGISwapChain* swap_chain, D3D11_TEXTURE2D_DESC& desc) {
    ID3D11Texture2D* back_buffer = nullptr;
    if (FAILED(swap_chain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back_buffer)))) {
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
    if (g_state != State::Disabled && swap_chain != g_swap_chain) {
        attach(swap_chain);
    }
    if (g_state != State::Running || swap_chain != g_swap_chain) {
        return;
    }
    // The view is created per frame so the overlay never keeps the game's back buffer alive.
    D3D11_TEXTURE2D_DESC desc{};
    ID3D11RenderTargetView* target = create_render_target(swap_chain, desc);
    if (target == nullptr) {
        return;
    }

    ImGui_ImplDX11_NewFrame();
    build_overlay_frame(desc.Width, desc.Height);

    ID3D11RenderTargetView* game_target = nullptr;
    ID3D11DepthStencilView* game_depth = nullptr;
    g_context->OMGetRenderTargets(1, &game_target, &game_depth);
    g_context->OMSetRenderTargets(1, &target, nullptr);
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
    g_context->OMSetRenderTargets(1, &game_target, game_depth);
    if (game_target != nullptr) {
        game_target->Release();
    }
    if (game_depth != nullptr) {
        game_depth->Release();
    }
    target->Release();
}

}  // namespace reflektortts
