// Reading a PE image (an EXE or a DLL) as Windows maps it: its headers, and what lies at an RVA,
// an offset from the image's start.

#pragma once

#include <windows.h>

#include <cstdint>

#include "memory/addresses.h"

namespace reflektortts {

// What lies at rva in the image mapped at base.
template <typename T>
const T* at_rva(const BYTE* base, std::uintptr_t rva) {
    return pointer_at<const T>(address_of(base) + rva);
}

// The image's NT headers, which the DOS header at its start points to.
inline const IMAGE_NT_HEADERS& pe_headers(const BYTE* base) {
    const auto* dos = object_at<const IMAGE_DOS_HEADER>(base);
    return *at_rva<IMAGE_NT_HEADERS>(base, static_cast<std::uintptr_t>(dos->e_lfanew));
}

}  // namespace reflektortts
