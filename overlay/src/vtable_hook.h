#pragma once

#include <windows.h>

namespace reflektortts {

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

}  // namespace reflektortts
