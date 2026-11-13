// Finding a function a module exports, as the type it has.

#pragma once

#include <windows.h>

namespace reflektortts {

// The function module exports under name, as Fn; nullptr if module is nullptr or exports no such
// function.
template <typename Fn>
Fn exported_function(HMODULE module, const char* name) {
    if (module == nullptr) {
        return nullptr;
    }
    // GetProcAddress gives every function as FARPROC. Casting through void (*)(), which stands for any
    // function, tells the compiler that the cast to the function's own type is meant.
    return reinterpret_cast<Fn>(reinterpret_cast<void (*)()>(GetProcAddress(module, name)));
}

}  // namespace reflektortts
