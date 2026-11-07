#include "ui.h"

#include <imgui.h>

#include <cfloat>

#include "api_client.h"
#include "input.h"
#include "settings_panel.h"
#include "subtitles.h"

namespace reflektortts {
namespace {

constexpr double kHintSeconds = 10.0;

void draw_hint() {
    ImGui::SetNextWindowPos(ImVec2(10.0f, 10.0f));
    ImGui::SetNextWindowBgAlpha(0.6f);
    ImGui::Begin("##hint", nullptr,
                 ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_AlwaysAutoResize |
                     ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav);
    ImGui::TextUnformatted("ReflektorTTS: Ctrl+Shift+R opens settings");
    ImGui::End();
}

void draw_panel(const CoreState& state) {
    ImGui::SetNextWindowPos(ImVec2(20.0f, 20.0f), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSizeConstraints(ImVec2(kSettingsPanelWidth, 0.0f), ImVec2(kSettingsPanelWidth, FLT_MAX));
    ImGui::Begin("ReflektorTTS", nullptr,
                 ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_AlwaysAutoResize);
    draw_settings_panel(state, PanelPlace::Overlay);
    ImGui::TextDisabled("Ctrl+Shift+R closes this panel");
    ImGui::End();
}

}  // namespace

void draw_ui() {
    CoreState state = core_state();
    draw_subtitle(state);
    if (panel_open()) {
        draw_panel(state);
    } else if (ImGui::GetTime() < kHintSeconds) {
        draw_hint();
    }
}

}  // namespace reflektortts
