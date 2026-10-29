#include "overlay_frame.h"

#include <imgui.h>
#include <imgui_impl_win32.h>

#include <string>

#include "log.h"
#include "ui.h"

namespace reflektortts {
namespace {

bool g_claimed = false;
HWND g_window = nullptr;

}  // namespace

bool claim_overlay(const char* api_name, HWND window) {
    if (g_claimed) {
        return false;
    }
    ImGui::CreateContext();
    ImGui::GetIO().IniFilename = nullptr;
    if (!ImGui_ImplWin32_Init(window)) {
        log_message("ImGui Win32 backend failed to initialize");
        ImGui::DestroyContext();
        return false;
    }
    g_claimed = true;
    g_window = window;
    log_message(std::string("Overlay attached to ") + api_name);
    return true;
}

void set_overlay_window(HWND window) {
    if (window == g_window) {
        return;
    }
    ImGui_ImplWin32_Shutdown();
    ImGui_ImplWin32_Init(window);
    g_window = window;
}

// Mirrors the backends' Shutdown functions minus every call into the device.
void forget_renderer_backend() {
    for (ImTextureData* texture : ImGui::GetPlatformIO().Textures) {
        if (texture->Status != ImTextureStatus_Destroyed) {
            texture->SetTexID(ImTextureID_Invalid);
            texture->BackendUserData = nullptr;
            texture->SetStatus(ImTextureStatus_Destroyed);
        }
    }
    ImGuiIO& io = ImGui::GetIO();
    io.BackendRendererName = nullptr;
    io.BackendRendererUserData = nullptr;
    io.BackendFlags &= ~(ImGuiBackendFlags_RendererHasVtxOffset | ImGuiBackendFlags_RendererHasTextures);
    ImGui::GetPlatformIO().ClearRendererHandlers();
}

void build_overlay_frame(UINT back_buffer_width, UINT back_buffer_height) {
    ImGui_ImplWin32_NewFrame();
    ImGui::GetIO().DisplaySize =
        ImVec2(static_cast<float>(back_buffer_width), static_cast<float>(back_buffer_height));
    ImGui::NewFrame();
    draw_ui();
    ImGui::Render();
}

}  // namespace reflektortts
