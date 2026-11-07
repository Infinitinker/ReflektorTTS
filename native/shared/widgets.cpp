#include "widgets.h"

namespace reflektortts {

void dot_label(ImU32 color, const char* label) {
    ImVec2 position = ImGui::GetCursorScreenPos();
    float radius = ImGui::GetFontSize() * 0.3f;
    float line = ImGui::GetTextLineHeight();
    ImGui::GetWindowDrawList()->AddCircleFilled(ImVec2(position.x + radius, position.y + line * 0.5f), radius, color);
    ImGui::Dummy(ImVec2(radius * 2.0f, line));
    ImGui::SameLine();
    ImGui::TextUnformatted(label);
}

float dot_label_width(const char* label) {
    return ImGui::GetFontSize() * 0.6f + ImGui::GetStyle().ItemSpacing.x + ImGui::CalcTextSize(label).x;
}

void align_right(float width) {
    ImGui::SameLine(ImGui::GetContentRegionMax().x - width);
}

void begin_box(const char* title) {
    ImGui::BeginChild(title, ImVec2(0.0f, 0.0f), ImGuiChildFlags_Borders | ImGuiChildFlags_AutoResizeY);
    ImGui::TextDisabled("%s", title);
}

void end_box() {
    ImGui::EndChild();
}

void begin_indented() {
    ImGui::Indent();
    ImGui::PushItemWidth(ImGui::CalcItemWidth() - ImGui::GetStyle().IndentSpacing);
}

void end_indented() {
    ImGui::PopItemWidth();
    ImGui::Unindent();
}

void begin_section(const char* title) {
    ImGui::TextUnformatted(title);
    begin_indented();
}

void end_section() {
    end_indented();
}

void draw_flow_arrow() {
    float size = ImGui::GetFontSize() * 0.5f;
    ImVec2 top = ImGui::GetCursorScreenPos();
    float center = top.x + ImGui::GetContentRegionAvail().x * 0.5f;
    ImGui::GetWindowDrawList()->AddTriangleFilled(ImVec2(center - size, top.y), ImVec2(center + size, top.y),
                                                  ImVec2(center, top.y + size), ImGui::GetColorU32(ImGuiCol_TextDisabled));
    ImGui::Dummy(ImVec2(0.0f, size));
}

void draw_choice_combo(const char* label, const std::string& current, std::span<const Choice> choices,
                       void (*request)(const std::string&)) {
    const char* shown = current.c_str();
    for (const Choice& choice : choices) {
        if (current == choice.value) {
            shown = choice.name;
        }
    }
    if (!ImGui::BeginCombo(label, shown)) {
        return;
    }
    for (const Choice& choice : choices) {
        bool selected = current == choice.value;
        if (ImGui::Selectable(choice.name, selected) && !selected) {
            request(choice.value);
        }
    }
    ImGui::EndCombo();
}

}  // namespace reflektortts
