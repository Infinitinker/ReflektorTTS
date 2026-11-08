#include "text_fit.h"

#include <cstddef>

namespace reflektortts {

std::vector<std::string> wrap_lines(ImFont* font, float size, const std::string& text, float width) {
    std::vector<std::string> lines;
    const char* start = text.c_str();
    const char* end = start + text.size();
    while (start < end) {
        const char* line_end = font->CalcWordWrapPosition(size, start, end, width);
        if (line_end == start) {
            ++line_end;
        }
        lines.emplace_back(start, line_end);
        start = line_end;
        while (start < end && (*start == ' ' || *start == '\n')) {
            ++start;
        }
    }
    return lines;
}

void clamped_wrapped_text(const std::string& text, int max_lines) {
    float width = ImGui::GetContentRegionAvail().x;
    std::vector<std::string> lines = wrap_lines(ImGui::GetFont(), ImGui::GetFontSize(), text, width);
    if (lines.size() > static_cast<std::size_t>(max_lines)) {
        lines.resize(max_lines);
        std::string& last = lines.back();
        while (!last.empty() && ImGui::CalcTextSize((last + "...").c_str()).x > width) {
            // Drop one UTF-8 character: its continuation bytes, then its first byte.
            while (!last.empty() && (static_cast<unsigned char>(last.back()) & 0xC0) == 0x80) {
                last.pop_back();
            }
            if (!last.empty()) {
                last.pop_back();
            }
        }
        last += "...";
    }
    for (const std::string& line : lines) {
        ImGui::TextUnformatted(line.c_str());
    }
}

std::string fit_width(const std::string& text, float width) {
    if (ImGui::CalcTextSize(text.c_str()).x <= width) {
        return text;
    }
    std::string cut = text;
    while (!cut.empty() && ImGui::CalcTextSize((cut + "...").c_str()).x > width) {
        cut.pop_back();
        while (!cut.empty() && (static_cast<unsigned char>(cut.back()) & 0xC0) == 0x80) {
            cut.pop_back();  // The rest of a UTF-8 character.
        }
    }
    return cut + "...";
}

}  // namespace reflektortts
