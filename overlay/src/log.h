#pragma once

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace reflektortts {

// Writes to the debugger output, readable with DebugView or an attached debugger.
inline void log_message(const std::string& message) {
    OutputDebugStringA(("[ReflektorTTS] " + message + "\n").c_str());
}

// "module+offset" for a code address, which stays the same between runs.
inline std::string describe_address(const void* address) {
    HMODULE module = nullptr;
    char path[MAX_PATH] = "?";
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCSTR>(address), &module)) {
        GetModuleFileNameA(module, path, MAX_PATH);
    }
    const char* name = std::strrchr(path, '\\') != nullptr ? std::strrchr(path, '\\') + 1 : path;
    char text[MAX_PATH + 32];
    std::snprintf(text, sizeof(text), "%s+0x%llX", name,
                  static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(address) -
                                                  reinterpret_cast<std::uintptr_t>(module)));
    return text;
}

}  // namespace reflektortts
