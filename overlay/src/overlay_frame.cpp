#include "overlay_frame.h"

#include <imgui.h>
#include <imgui_impl_win32.h>

#include <filesystem>
#include <string>

#include "input.h"
#include "log.h"
#include "ui.h"

namespace reflektortts {
namespace {

constexpr float kFontSize = 16.0f;

bool g_claimed = false;
HWND g_window = nullptr;

// ImGui's built-in font covers basic Latin only; Segoe UI also has Polish and other
// accented letters, and ImGui loads glyphs from it on demand.
void load_system_font() {
    wchar_t windows_dir[MAX_PATH];
    if (GetWindowsDirectoryW(windows_dir, MAX_PATH) == 0) {
        return;
    }
    std::filesystem::path font = std::filesystem::path(windows_dir) / L"Fonts" / L"segoeui.ttf";
    if (!std::filesystem::exists(font) ||
        ImGui::GetIO().Fonts->AddFontFromFileTTF(font.string().c_str(), kFontSize) == nullptr) {
        log_message("Segoe UI not found; accented letters may not display");
    }
}

}  // namespace

bool claim_overlay(const char* api_name, HWND window) {
    if (g_claimed) {
        return false;
    }
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;
    load_system_font();
    if (!ImGui_ImplWin32_Init(window)) {
        log_message("ImGui Win32 backend failed to initialize");
        ImGui::DestroyContext();
        return false;
    }
    attach_input(window);
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
    attach_input(window);
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
    // ImGui works in window coordinates, where the mouse is; the image is scaled to the
    // back buffer, which can differ in size when the game or a wrapper scales its image.
    ImGuiIO& io = ImGui::GetIO();
    if (io.DisplaySize.x > 0 && io.DisplaySize.y > 0) {
        io.DisplayFramebufferScale = ImVec2(static_cast<float>(back_buffer_width) / io.DisplaySize.x,
                                            static_cast<float>(back_buffer_height) / io.DisplaySize.y);
    } else {
        io.DisplaySize = ImVec2(static_cast<float>(back_buffer_width), static_cast<float>(back_buffer_height));
        io.DisplayFramebufferScale = ImVec2(1.0f, 1.0f);
    }
    update_panel_toggle(g_window);
    ImGui::NewFrame();
    draw_ui();
    ImGui::Render();
}

}  // namespace reflektortts
