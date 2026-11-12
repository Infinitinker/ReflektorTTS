// The subtitles over the app: the current line, centered at the top or bottom of the screen on a
// dark band, in the size the settings ask for.

#include "ui/subtitles.h"

#include <imgui.h>

#include <algorithm>
#include <cfloat>
#include <cstddef>
#include <string>
#include <vector>

#include "text_fit.h"

namespace reflektortts {
namespace {

constexpr float kSubtitleWidth = 0.7f;   // Of the screen's width.
constexpr float kSubtitleMargin = 0.05f;  // Of the screen's height, from its top or bottom edge.
constexpr float kMinSubtitleFontSize = 16.0f;

float subtitle_font_size(const std::string& size, float screen_height) {
    float share = size == "small" ? 0.03f : size == "large" ? 0.05f : 0.04f;
    return std::max(kMinSubtitleFontSize, screen_height * share);
}

}  // namespace

void draw_subtitle(const CoreState& state) {
    if (state.subtitle.empty()) {
        return;
    }
    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImFont* font = ImGui::GetFont();
    float size = subtitle_font_size(state.settings.subtitle_size, viewport->Size.y);
    std::vector<std::string> lines = wrap_lines(font, size, state.subtitle, viewport->Size.x * kSubtitleWidth);
    std::vector<float> widths;
    float widest = 0.0f;
    for (const std::string& line : lines) {
        widths.push_back(font->CalcTextSizeA(size, FLT_MAX, 0.0f, line.c_str()).x);
        widest = std::max(widest, widths.back());
    }
    ImVec2 padding(size * 0.5f, size * 0.25f);
    ImVec2 band(widest + padding.x * 2.0f, size * static_cast<float>(lines.size()) + padding.y * 2.0f);
    float margin = viewport->Size.y * kSubtitleMargin;
    float x = viewport->Pos.x + (viewport->Size.x - band.x) * 0.5f;
    float y = state.settings.subtitle_position == "bottom" ? viewport->Pos.y + viewport->Size.y - margin - band.y
                                                  : viewport->Pos.y + margin;
    ImDrawList* draw = ImGui::GetBackgroundDrawList();
    draw->AddRectFilled(ImVec2(x, y), ImVec2(x + band.x, y + band.y), IM_COL32(0, 0, 0, 160), size * 0.25f);
    for (std::size_t i = 0; i < lines.size(); ++i) {
        ImVec2 position(x + padding.x + (widest - widths[i]) * 0.5f, y + padding.y + size * static_cast<float>(i));
        draw->AddText(font, size, position, IM_COL32(255, 255, 255, 255), lines[i].c_str());
    }
}

}  // namespace reflektortts
