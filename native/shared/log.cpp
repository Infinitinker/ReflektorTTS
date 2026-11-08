#include "log.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <cstdio>
#endif

namespace reflektortts {

void log_message(const std::string& message) {
    std::string line = "[ReflektorTTS] " + message + "\n";
#ifdef _WIN32
    OutputDebugStringA(line.c_str());
#else
    std::fputs(line.c_str(), stderr);
#endif
}

}  // namespace reflektortts
