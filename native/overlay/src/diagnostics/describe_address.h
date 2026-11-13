// Names a code address as module and offset, for the log: unlike the address itself, it stays the
// same between runs.

#pragma once

#include <windows.h>

#include <cstdint>
#include <cstring>
#include <format>
#include <string>

#include "memory/addresses.h"

namespace reflektortts {

// "module+offset" for a code address, which stays the same between runs.
inline std::string describe_address(const void* address) {
    HMODULE module = nullptr;
    char path[MAX_PATH] = "?";
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCSTR>(address), &module)) {
        GetModuleFileNameA(module, path, MAX_PATH);
    }
    const char* name = std::strrchr(path, '\\') != nullptr ? std::strrchr(path, '\\') + 1 : path;
    return std::format("{}+0x{:X}", name, address_of(address) - address_of(module));
}

}  // namespace reflektortts
