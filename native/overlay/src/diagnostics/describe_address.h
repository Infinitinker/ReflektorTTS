// Names a code address as module and offset, for the log: unlike the address itself, it stays the
// same between runs.

#pragma once

#include <windows.h>

#include <array>
#include <cstdint>
#include <format>
#include <string>
#include <string_view>

#include "memory/addresses.h"

namespace reflektortts {

// "module+offset" for a code address, which stays the same between runs.
inline std::string describe_address(const void* address) {
    HMODULE module = nullptr;
    std::array<char, MAX_PATH> path{'?'};
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCSTR>(address), &module)) {
        GetModuleFileNameA(module, path.data(), MAX_PATH);
    }
    std::string_view full(path.data());
    // The file name after the last backslash; the whole path if it has none (npos + 1 is 0).
    std::string_view name = full.substr(full.rfind('\\') + 1);
    return std::format("{}+0x{:X}", name, address_of(address) - address_of(module));
}

}  // namespace reflektortts
