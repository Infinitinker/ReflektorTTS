#include "panel_ui.h"

#include <imgui.h>

#include "settings_panel.h"

namespace reflektortts {

void draw_panel_ui(const CoreState& state) {
    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(viewport->WorkPos);
    ImGui::SetNextWindowSize(viewport->WorkSize);
    // The SDL window has the frame, so this one has neither rounded corners nor a border.
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 0.0f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::Begin("##settings", nullptr,
                 ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove |
                     ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_NoBringToFrontOnFocus);
    ImGui::PopStyleVar(2);
    draw_settings_panel(state, PanelPlace::Window);
    ImGui::End();
}

std::string window_title(const CoreState& state) {
    return state.app.empty() ? "Settings - ReflektorTTS" : state.app + " settings - ReflektorTTS";
}

}  // namespace reflektortts
