// Tells the user why the panel cannot start: on standard error, which the desktop app reads, in
// the log, and in a message box.

#pragma once

#include <string>

namespace reflektortts {

// Tells the user why the panel cannot start: on standard error (read by the desktop app that
// started it), in the log, and in a message box.
void report_startup_error(const std::string& message);

}  // namespace reflektortts
