// Addresses as integers and the objects at them, for code that reads memory by its layout: hooks,
// raw input blocks, PE headers and the call stack. Each cast is here, once, with why it is needed.

#pragma once

#include <windows.h>

#include <cstdint>
#include <type_traits>

namespace reflektortts {

// An address as an integer, to compute with: an offset from a module's start, or the next aligned
// address.
inline std::uintptr_t address_of(const void* pointer) {
    // An integer is the only way to compute with an address that is not in one array.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<std::uintptr_t>(pointer);
}

// What lies at an address given as an integer: one computed with address_of, or one Windows hands
// over as an integer (a CPU register, the slot of a 32-bit jump, a thread's parameter).
template <typename T>
T* pointer_at(std::uintptr_t address) {
    // Such an address names memory that only Windows or the app knows the layout of.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast,performance-no-int-to-ptr)
    return reinterpret_cast<T*>(address);
}

// The bytes at bytes as the structure Windows lays out there, such as a raw input header; T is const
// for const bytes.
template <typename T, typename Byte>
T* object_at(Byte* bytes) {
    static_assert(std::is_same_v<std::remove_const_t<Byte>, BYTE>, "object_at reads bytes");
    // Windows hands such structures over in byte buffers, each at an offset it gives.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<T*>(bytes);
}

// The bytes of an object, to step through a buffer Windows fills with structures of varying size.
template <typename T>
BYTE* bytes_of(T* object) {
    // Any object may be read and written as bytes.
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return reinterpret_cast<BYTE*>(object);
}

}  // namespace reflektortts
