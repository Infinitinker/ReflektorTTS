#pragma once

#include <windows.h>

#include <cstdio>
#include <string>

#include "code_hook.h"
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
// Patching the table instead of the function's code keeps working when other overlays
// (RTSS, Steam, Discord) re-apply their own code hooks; our detour runs first and then
// calls whatever the entry pointed to, including their hooks.
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

// Points a COM method at detour, for every object of the vtable's class: by patching the vtable
// entry, or, where the process refuses to make the vtable writable, by hooking the method's code.
// Either way *original reaches the method as it was.
template <typename Fn>
bool hook_method(void** vtable, int index, Fn detour, Fn* original) {
    void* method = vtable[index];
    // Already ours (hooked before): hooking again would make the detour call itself.
    if (method == reinterpret_cast<void*>(detour)) {
        return true;
    }
    if (hook_vtable_entry(vtable, index, detour, original)) {
        return true;
    }
    log_message("Cannot patch a vtable (" + describe_memory(&vtable[index]) + "); hooking the method's code instead");
    return hook_function(method, reinterpret_cast<void*>(detour), reinterpret_cast<void**>(original));
}

}  // namespace reflektortts
