// Small ImGui helpers shared by the settings panel's boxes, and the colors it marks states and
// errors with.

#pragma once

#include <imgui.h>

#include <span>
#include <string>
#include <string_view>

namespace reflektortts {

inline constexpr ImVec4 kErrorColor(1.0f, 0.45f, 0.4f, 1.0f);
inline constexpr ImVec4 kWarningColor(1.0f, 0.75f, 0.3f, 1.0f);
inline constexpr ImU32 kGreen = IM_COL32(90, 200, 110, 255);
inline constexpr ImU32 kAmber = IM_COL32(240, 180, 60, 255);
inline constexpr ImU32 kGray = IM_COL32(140, 140, 140, 255);

// ImGui's flags are values of int enums. They are combined and cleared as the bits they are, on
// unsigned values, and handed back as the int ImGui takes.
template <typename... Flags>
constexpr int combined_flags(Flags... flags) {
    return static_cast<int>((0U | ... | static_cast<unsigned>(flags)));
}
constexpr int without_flags(int flags, int removed) {
    return static_cast<int>(static_cast<unsigned>(flags) & ~static_cast<unsigned>(removed));
}

// Text as it is: ImGui's Text functions take a printf format instead, which "%s" would have to pass
// it through. Grayed out, in a color, wrapped at the window's edge, or as the hovered item's tooltip.
void disabled_text(std::string_view text);
void colored_text(const ImVec4& color, std::string_view text);
void wrapped_text(std::string_view text);
void tooltip(std::string_view text);

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
