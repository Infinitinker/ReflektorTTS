// Fits text to a width in ImGui: wrapped into lines, cut after a number of lines, or cut to one
// line, ending in "…" where it does not fit.

#include "text_fit.h"

#include <algorithm>
#include <cstddef>
#include <memory>
#include <string_view>

namespace reflektortts {

namespace {

// Ends text cut where it does not fit; Segoe UI, the font the overlay and the settings window use, has it.
constexpr const char* kEllipsis = "…";

// Drops the text's last UTF-8 character: its continuation bytes, then its first byte, so no first
// byte is left without the rest of its character.
void drop_last_character(std::string& text) {
    while (!text.empty() && (static_cast<unsigned char>(text.back()) & 0xC0) == 0x80) {
        text.pop_back();
    }
    if (!text.empty()) {
        text.pop_back();
    }
}

}  // namespace

std::vector<std::string> wrap_lines(ImFont* font, float size, const std::string& text, float width) {
    std::vector<std::string> lines;
    std::string_view rest = text;
    while (!rest.empty()) {
        const char* start = std::to_address(rest.begin());
        const char* line_end = font->CalcWordWrapPosition(size, start, std::to_address(rest.end()), width);
        // A line holds at least one character, even one wider than the width.
        std::size_t length = std::max<std::size_t>(static_cast<std::size_t>(line_end - start), 1);
        lines.emplace_back(rest.substr(0, length));
        rest.remove_prefix(length);
        rest.remove_prefix(std::min(rest.find_first_not_of(" \n"), rest.size()));
    }
    return lines;
}

void clamped_wrapped_text(const std::string& text, int max_lines) {
    float width = ImGui::GetContentRegionAvail().x;
    std::vector<std::string> lines = wrap_lines(ImGui::GetFont(), ImGui::GetFontSize(), text, width);
    if (lines.size() > static_cast<std::size_t>(max_lines)) {
        lines.resize(static_cast<std::size_t>(max_lines));
        std::string& last = lines.back();
        while (!last.empty() && ImGui::CalcTextSize((last + kEllipsis).c_str()).x > width) {
            drop_last_character(last);
        }
        last += kEllipsis;
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
    while (!cut.empty() && ImGui::CalcTextSize((cut + kEllipsis).c_str()).x > width) {
        drop_last_character(cut);
    }
    return cut + kEllipsis;
}

}  // namespace reflektortts
