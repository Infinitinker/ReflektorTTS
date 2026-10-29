#include "d3d9_renderer.h"

#include <imgui.h>
#include <imgui_impl_dx9.h>

#include "log.h"
#include "overlay_frame.h"

namespace reflektortts {
namespace {

enum class State { NotStarted, Running, Disabled };

State g_state = State::NotStarted;
IDirect3DDevice9* g_device = nullptr;

HWND device_window(IDirect3DDevice9* device) {
    D3DDEVICE_CREATION_PARAMETERS creation{};
    device->GetCreationParameters(&creation);
    if (creation.hFocusWindow != nullptr) {
        return creation.hFocusWindow;
    }
    IDirect3DSwapChain9* swap_chain = nullptr;
    if (FAILED(device->GetSwapChain(0, &swap_chain))) {
        return nullptr;
    }
    D3DPRESENT_PARAMETERS parameters{};
    swap_chain->GetPresentParameters(&parameters);
    swap_chain->Release();
    return parameters.hDeviceWindow;
}

// Games may create a new device, e.g. when switching from the menu to gameplay, so the
// overlay follows the device that presented last.
void attach(IDirect3DDevice9* device) {
    HWND window = device_window(device);
    if (g_state == State::NotStarted && !claim_overlay("Direct3D 9", window)) {
        g_state = State::Disabled;
        return;
    }
    set_overlay_window(window);
    // A replaced device is abandoned, never released (see forget_renderer_backend).
    if (g_device != nullptr) {
        forget_renderer_backend();
    }
    if (!ImGui_ImplDX9_Init(device)) {
        log_message("ImGui Direct3D 9 backend failed to initialize; overlay disabled");
        g_state = State::Disabled;
        return;
    }
    g_device = device;
    g_state = State::Running;
}

}  // namespace

void render_d3d9_frame(IDirect3DDevice9* device) {
    if (g_state != State::Disabled && device != g_device) {
        attach(device);
    }
    if (g_state != State::Running || device != g_device) {
        return;
    }

    // The game may have left a texture as the render target; draw on the back buffer.
    IDirect3DSurface9* back_buffer = nullptr;
    IDirect3DSurface9* game_target = nullptr;
    if (FAILED(device->GetBackBuffer(0, 0, D3DBACKBUFFER_TYPE_MONO, &back_buffer))) {
        return;
    }
    D3DSURFACE_DESC desc{};
    back_buffer->GetDesc(&desc);
    ImGui_ImplDX9_NewFrame();
    build_overlay_frame(desc.Width, desc.Height);

    device->GetRenderTarget(0, &game_target);
    device->SetRenderTarget(0, back_buffer);
    if (SUCCEEDED(device->BeginScene())) {
        ImGui_ImplDX9_RenderDrawData(ImGui::GetDrawData());
        device->EndScene();
    }
    device->SetRenderTarget(0, game_target);
    back_buffer->Release();
    if (game_target != nullptr) {
        game_target->Release();
    }
}

void release_d3d9_device_objects(IDirect3DDevice9* device) {
    if (g_state == State::Running && device == g_device) {
        ImGui_ImplDX9_InvalidateDeviceObjects();
    }
}

void recreate_d3d9_device_objects(IDirect3DDevice9* device) {
    if (g_state == State::Running && device == g_device) {
        ImGui_ImplDX9_CreateDeviceObjects();
    }
}

}  // namespace reflektortts
