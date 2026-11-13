// The settings panel's Processing box, drawn by settings_panel.cpp between the Input and Output
// boxes.

#pragma once

#include "core_state.h"

namespace reflektortts {

// The Processing box: the stages each line passes through, switched on and off for the text
// shown and for speech.
void draw_processing(const ProfileSettings& settings);

}  // namespace reflektortts
