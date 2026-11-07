#pragma once

#include "core_state.h"

namespace reflektortts {

// The settings panel's contents, in the current ImGui window: a header with the connection state,
// then, while connected, the app being read and the Input, Processing, Output and Last line boxes,
// and the last error with a button to dismiss it.
void draw_settings_panel(const CoreState& state);

}  // namespace reflektortts
