#pragma once

#include <imgui.h>

#include <string>
#include <vector>

namespace reflektortts {

// Splits text into lines no wider than width in the given font and size, breaking between words.
std::vector<std::string> wrap_lines(ImFont* font, float size, const std::string& text, float width);

// Text wrapped to the current window, cut after max_lines lines with "..." so it never grows past them.
void clamped_wrapped_text(const std::string& text, int max_lines);

// The text cut to fit width in the current font, ending in "..." if it does not fit whole.
std::string fit_width(const std::string& text, float width);

}  // namespace reflektortts
