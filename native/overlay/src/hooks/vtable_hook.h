#pragma once

#include <windows.h>

#include <cstdio>
#include <string>

#include "hooks/code_hook.h"
#include "log.h"

namespace reflektortts {

// Why a vtable could not be patched, for the log: the last error, and the memory's protection
// and owning module.
inline std::string describe_memory(const void* address) {
    DWORD error = GetLastError();
    MEMORY_BASIC_INFORMATION info{};
    VirtualQuery(address, &info, sizeof(info));
    wchar_t module[MAX_PATH] = L"?";
    HMODULE handle = nullptr;
    if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCWSTR>(address), &handle)) {
        GetModuleFileNameW(handle, module, MAX_PATH);
    }
    char text[512];
    std::snprintf(text, sizeof(text), "error %lu, address %p, protection 0x%lx, type 0x%lx, module %ls", error,
                  address, info.Protect, info.Type, module);
    return text;
}

// Replaces one entry of a COM vtable with detour and stores the previous entry in original.
template <typename Fn>
bool hook_vtable_entry(void** vtable, int index, Fn detour, Fn* original) {
    DWORD protection = 0;
    if (!VirtualProtect(&vtable[index], sizeof(void*), PAGE_READWRITE, &protection)) {
        return false;
    }
    *original = reinterpret_cast<Fn>(vtable[index]);
    vtable[index] = reinterpret_cast<void*>(detour);
    VirtualProtect(&vtable[index], sizeof(void*), protection, &protection);
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
    if (method == reinterpret_cast<void*>(detour)) {
        return true;
    }
    if (hook_function(method, reinterpret_cast<void*>(detour), reinterpret_cast<void**>(original))) {
        return true;
    }
    log_message("Cannot hook a method's code; patching its vtable entry instead");
    if (hook_vtable_entry(vtable, index, detour, original)) {
        return true;
    }
    log_message("Cannot patch a vtable either (" + describe_memory(&vtable[index]) + ")");
    return false;
}

}  // namespace reflektortts
