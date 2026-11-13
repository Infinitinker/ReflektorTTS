// Hooks a COM method found through a vtable: in its code, so it chains with other overlays' hooks,
// or, where that fails, by replacing the vtable entry.

#pragma once

#include <windows.h>

#include <format>
#include <string>

#include "diagnostics/describe_address.h"
#include "hooks/code_hook.h"
#include "log.h"
#include "memory/functions.h"

namespace reflektortts {

// Why a vtable could not be patched, for the log: the last error, the memory's protection and type,
// and where it is, as module and offset.
inline std::string describe_memory(const void* address) {
    DWORD error = GetLastError();
    MEMORY_BASIC_INFORMATION info{};
    VirtualQuery(address, &info, sizeof(info));
    return std::format("error {}, address {}, protection 0x{:x}, type 0x{:x}, at {}", error, address, info.Protect,
                       info.Type, describe_address(address));
}

// The vtable of a COM object: the first thing in it.
inline void** vtable_of(void* object) {
    return *static_cast<void***>(object);
}

// Replaces one entry of a COM vtable with detour and stores the previous entry in original.
template <typename Fn>
bool hook_vtable_entry(void** vtable, int index, Fn detour, Fn* original) {
    DWORD protection = 0;
    if (!VirtualProtect(static_cast<void*>(&vtable[index]), sizeof(void*), PAGE_READWRITE, &protection)) {
        return false;
    }
    *original = function_at<Fn>(vtable[index]);
    vtable[index] = code_address(detour);
    VirtualProtect(static_cast<void*>(&vtable[index]), sizeof(void*), protection, &protection);
    return true;
}

// Points a COM method at detour, for every object of the vtable's class, and stores in *original
// a way to reach the method as it was. The method's code is hooked, as other overlays (Steam,
// RTSS, Discord, OBS) hook it, so all of them chain: each code hook carries the jump of the one
// before it, whichever came first, and the chain ends at the method. A vtable entry does not
// chain with them: the Steam overlay calls the entry it finds there as the next hook after its
// own, while ours calls the method, whose code begins with Steam's jump, and the two call each
// other until the stack runs out. Apps that keep the method's address instead of reading the
// vtable each frame are caught as well. Patching the vtable remains the fallback.
template <typename Fn>
bool hook_method(void** vtable, int index, Fn detour, Fn* original) {
    void* method = vtable[index];
    // Already ours (hooked before): hooking again would make the detour call itself.
    if (method == code_address(detour)) {
        return true;
    }
    if (hook_function(method, code_address(detour), function_slot(original))) {
        return true;
    }
    log_message("Cannot hook a method's code; patching its vtable entry instead");
    if (hook_vtable_entry(vtable, index, detour, original)) {
        return true;
    }
    log_message("Cannot patch a vtable either (" + describe_memory(static_cast<void*>(&vtable[index])) + ")");
    return false;
}

}  // namespace reflektortts
