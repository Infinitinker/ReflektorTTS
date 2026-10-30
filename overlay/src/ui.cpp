#include "ui.h"

#include <imgui.h>

#include <string>

#include "api_client.h"
#include "input.h"

namespace reflektortts {
namespace {

constexpr double kHintSeconds = 10.0;
constexpr ImVec4 kErrorColor(1.0f, 0.45f, 0.4f, 1.0f);

void draw_hint() {
    ImGui::SetNextWindowPos(ImVec2(10.0f, 10.0f));
    ImGui::SetNextWindowBgAlpha(0.6f);
    ImGui::Begin("##hint", nullptr,
                 ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_AlwaysAutoResize |
                     ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav);
    ImGui::TextUnformatted("ReflektorTTS: Ctrl+Shift+R opens settings");
    ImGui::End();
}

std::string voice_label(const CoreState& state) {
    for (const VoiceOption& voice : state.voices) {
        if (voice.id == state.voice) {
            return voice.name + " (" + voice.language + ")";
        }
    }
    return state.voice;
}

void draw_voice_picker(const CoreState& state) {
    if (!ImGui::BeginCombo("Voice", voice_label(state).c_str())) {
        return;
    }
    for (const VoiceOption& voice : state.voices) {
        std::string label = voice.name + " (" + voice.language + ")##" + voice.id;
        bool selected = voice.id == state.voice;
        if (ImGui::Selectable(label.c_str(), selected) && !selected) {
            request_voice(voice.id);
        }
        if (selected) {
            ImGui::SetItemDefaultFocus();
        }
    }
    ImGui::EndCombo();
}

void draw_panel(const CoreState& state) {
    ImGui::SetNextWindowPos(ImVec2(20.0f, 20.0f), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(380.0f, 0.0f), ImGuiCond_FirstUseEver);
    ImGui::Begin("ReflektorTTS", nullptr, ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings);
    if (!state.connected) {
        ImGui::TextWrapped("Not connected to ReflektorTTS. Is it running?");
    } else {
        ImGui::Text("Game: %s", state.game.empty() ? "none" : state.game.c_str());
        ImGui::Separator();
        ImGui::TextDisabled("Last line");
        ImGui::TextWrapped("%s", state.last_line.empty() ? "-" : state.last_line.c_str());
        ImGui::Separator();
        if (ImGui::Button(state.paused ? "Resume reading" : "Pause reading")) {
            request_paused(!state.paused);
        }
        draw_voice_picker(state);
    }
    if (!state.last_error.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, kErrorColor);
        ImGui::TextWrapped("%s", state.last_error.c_str());
        ImGui::PopStyleColor();
    }
    ImGui::TextDisabled("Ctrl+Shift+R closes this panel");
    ImGui::End();
}

}  // namespace

void draw_ui() {
    if (panel_open()) {
        draw_panel(core_state());
    } else if (ImGui::GetTime() < kHintSeconds) {
        draw_hint();
    }
}

}  // namespace reflektortts
