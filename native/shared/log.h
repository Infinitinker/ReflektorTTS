#pragma once

#include <string>

namespace reflektortts {

// Writes a line to the debugger output on Windows (readable with DebugView or an attached
// debugger), and to standard error elsewhere.
void log_message(const std::string& message);

}  // namespace reflektortts
