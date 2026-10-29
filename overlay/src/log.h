#pragma once

#include <windows.h>

#include <string>

namespace reflektortts {

// Writes to the debugger output, readable with DebugView or an attached debugger.
inline void log_message(const std::string& message) {
    OutputDebugStringA(("[ReflektorTTS] " + message + "\n").c_str());
}

}  // namespace reflektortts
