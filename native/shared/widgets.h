#pragma once

#include <imgui.h>

#include <span>
#include <string>

namespace reflektortts {

inline constexpr ImVec4 kErrorColor(1.0f, 0.45f, 0.4f, 1.0f);
inline constexpr ImVec4 kWarningColor(1.0f, 0.75f, 0.3f, 1.0f);
inline constexpr ImU32 kGreen = IM_COL32(90, 200, 110, 255);
inline constexpr ImU32 kAmber = IM_COL32(240, 180, 60, 255);
inline constexpr ImU32 kGray = IM_COL32(140, 140, 140, 255);

// A colored dot followed by a label, on the current line.
void dot_label(ImU32 color, const char* label);
float dot_label_width(const char* label);

// Puts the next item on the current line, ending at the right edge.
void align_right(float width);

// A bordered box whose height follows its contents.
void begin_box(const char* title);
void end_box();

// Indents the controls that follow, narrowed by the indent so their labels still line up with the rest.
void begin_indented();
void end_indented();

// A sub-heading with its controls indented under it.
void begin_section(const char* title);
void end_section();

// A small arrow between groups, showing which way text flows through ReflektorTTS.
void draw_flow_arrow();

// A setting's value as the core knows it, and its name in the panel.
struct Choice {
    const char* value;
    const char* name;
};

// A combo box of choices, which calls request with the value picked when it differs from current.
void draw_choice_combo(const char* label, const std::string& current, std::span<const Choice> choices,
                       void (*request)(const std::string&));

}  // namespace reflektortts
