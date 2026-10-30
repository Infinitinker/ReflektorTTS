#pragma once

#include <windows.h>

namespace reflektortts {

// Hooks an exported function by rewriting its first instructions (MinHook), for APIs that are
// plain functions rather than COM methods. Calls through *original reach the real function.
// Hooking a function that is already hooked does nothing and succeeds.
bool hook_function(void* target, void* detour, void** original);

// Hooks the function a module exports under name (or an ordinal from MAKEINTRESOURCEA).
template <typename Fn>
bool hook_export(HMODULE module, const char* name, Fn detour, Fn* original) {
    FARPROC target = module == nullptr ? nullptr : GetProcAddress(module, name);
    return target != nullptr && hook_function(reinterpret_cast<void*>(target), reinterpret_cast<void*>(detour),
                                              reinterpret_cast<void**>(original));
}

// Whether a code address lies in the overlay DLL. Input hooks let the overlay's own calls
// through, so the panel (and ImGui) keep seeing real input while the game does not.
bool is_overlay_code(const void* address);

// The overlay DLL's module handle.
HMODULE overlay_module();

}  // namespace reflektortts
