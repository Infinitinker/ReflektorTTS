// Loads the system's interface font as ImGui's default font: unlike ImGui's built-in one, it has
// accented letters.

#pragma once

namespace reflektortts {

// Adds the system's interface font to ImGui's font atlas at size, as the default font. ImGui's
// built-in font covers basic Latin only; this one also has Polish and other accented letters, and
// ImGui loads glyphs from it on demand. Returns false (after logging why) if there is none to add,
// so the built-in font is used.
bool load_system_font(float size);

}  // namespace reflektortts
