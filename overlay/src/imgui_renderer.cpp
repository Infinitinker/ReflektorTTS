#include "imgui_renderer.h"

#include <d3d11.h>
#include <imgui.h>
#include <imgui_impl_dx11.h>
#include <imgui_impl_win32.h>

#include "log.h"
#include "ui.h"

namespace reflektortts {
namespace {

enum class State { NotStarted, Running, Disabled };

State g_state = State::NotStarted;
IDXGISwapChain* g_swap_chain = nullptr;
ID3D11Device* g_device = nullptr;
ID3D11DeviceContext* g_context = nullptr;
ID3D11RenderTargetView* g_render_target = nullptr;

bool initialize(IDXGISwapChain* swap_chain) {
    if (FAILED(swap_chain->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&g_device)))) {
        log_message("The game's swap chain is not Direct3D 11; overlay disabled");
        return false;
    }
    g_device->GetImmediateContext(&g_context);

    DXGI_SWAP_CHAIN_DESC desc{};
    swap_chain->GetDesc(&desc);

    ImGui::CreateContext();
    ImGui::GetIO().IniFilename = nullptr;
    if (!ImGui_ImplWin32_Init(desc.OutputWindow) || !ImGui_ImplDX11_Init(g_device, g_context)) {
        log_message("ImGui backends failed to initialize; overlay disabled");
        return false;
    }
    g_swap_chain = swap_chain;
    log_message("Overlay attached to the game's swap chain");
    return true;
}

bool create_render_target() {
    ID3D11Texture2D* back_buffer = nullptr;
    if (FAILED(g_swap_chain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back_buffer)))) {
        return false;
    }
    HRESULT result = g_device->CreateRenderTargetView(back_buffer, nullptr, &g_render_target);
    back_buffer->Release();
    return SUCCEEDED(result);
}

}  // namespace

void render_overlay_frame(IDXGISwapChain* swap_chain) {
    if (g_state == State::NotStarted) {
        g_state = initialize(swap_chain) ? State::Running : State::Disabled;
    }
    // Games may present to more than one swap chain; draw only on the first one.
    if (g_state != State::Running || swap_chain != g_swap_chain) {
        return;
    }
    if (g_render_target == nullptr && !create_render_target()) {
        return;
    }

    ImGui_ImplDX11_NewFrame();
    ImGui_ImplWin32_NewFrame();
    ImGui::NewFrame();
    draw_ui();
    ImGui::Render();

    ID3D11RenderTargetView* game_target = nullptr;
    ID3D11DepthStencilView* game_depth = nullptr;
    g_context->OMGetRenderTargets(1, &game_target, &game_depth);
    g_context->OMSetRenderTargets(1, &g_render_target, nullptr);
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
    g_context->OMSetRenderTargets(1, &game_target, game_depth);
    if (game_target != nullptr) {
        game_target->Release();
    }
    if (game_depth != nullptr) {
        game_depth->Release();
    }
}

void release_overlay_render_target(IDXGISwapChain* swap_chain) {
    if (swap_chain == g_swap_chain && g_render_target != nullptr) {
        g_render_target->Release();
        g_render_target = nullptr;
    }
}

}  // namespace reflektortts
