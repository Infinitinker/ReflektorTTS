// Runs the panel's window: opens it, beside the desktop app's window or centered, and draws the
// API client's state in it until the user closes it.

#pragma once

#include <optional>

#include "arguments.h"

namespace reflektortts {

// Opens the panel's window, beside the desktop app's if dock is given, and runs it until the user
// closes it, drawing the API client's state. Returns the process's exit code: 0, or 1 (after
// telling the user why) if the window cannot open.
int run_panel_window(const std::optional<Dock>& dock);

}  // namespace reflektortts
