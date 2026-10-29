#include "ui.h"

#include <imgui.h>

namespace reflektortts {

void draw_ui() {
    ImGui::SetNextWindowPos(ImVec2(20.0f, 20.0f), ImGuiCond_FirstUseEver);
    ImGui::Begin("ReflektorTTS", nullptr, ImGuiWindowFlags_AlwaysAutoResize);
    ImGui::TextUnformatted("Hello, world!");
    ImGui::End();
}

}  // namespace reflektortts
