// Functions as code addresses and back, for hooks: MinHook and vtables hold functions as void*.
// Each cast is here, once, with why it is needed.

#pragma once

namespace reflektortts {

// Where a function's code starts, as MinHook and vtables take it.
template <typename Fn>
void* code_address(Fn function) {
    // Windows, where the overlay runs, keeps code and data addresses alike.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<void*>(function);
}

// The function whose code starts at address, such as a vtable entry, as the type it has.
template <typename Fn>
Fn function_at(void* address) {
    // Windows, where the overlay runs, keeps code and data addresses alike.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<Fn>(address);
}

// A variable that holds a function, as the void* slot MinHook writes the original function's
// trampoline into.
template <typename Fn>
void** function_slot(Fn* slot) {
    // A function pointer has the size and layout of a void* on Windows, where the overlay runs.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<void**>(slot);
}

}  // namespace reflektortts
