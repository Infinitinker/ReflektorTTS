#include "code_hook.h"

#include <MinHook.h>

#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>

#include "log.h"

namespace reflektortts {
namespace {

std::mutex g_mutex;
bool g_initialized = false;
std::unordered_map<void*, void*> g_trampolines;  // Hooked function -> its trampoline.

struct ModuleRange {
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
};

ModuleRange overlay_range() {
    static const ModuleRange range = [] {
        auto base = reinterpret_cast<std::uintptr_t>(overlay_module());
        auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
        auto nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
        return ModuleRange{base, base + nt->OptionalHeader.SizeOfImage};
    }();
    return range;
}

}  // namespace

bool hook_function(void* target, void* detour, void** original) {
    std::lock_guard lock(g_mutex);
    if (auto hooked = g_trampolines.find(target); hooked != g_trampolines.end()) {
        *original = hooked->second;
        return true;
    }
    if (!g_initialized) {
        MH_STATUS status = MH_Initialize();
        if (status != MH_OK && status != MH_ERROR_ALREADY_INITIALIZED) {
            log_message(std::string("Cannot start MinHook: ") + MH_StatusToString(status));
            return false;
        }
        g_initialized = true;
    }
    MH_STATUS status = MH_CreateHook(target, detour, original);
    if (status == MH_OK) {
        status = MH_EnableHook(target);
    }
    if (status != MH_OK) {
        log_message(std::string("Cannot hook a function: ") + MH_StatusToString(status));
        return false;
    }
    g_trampolines[target] = *original;
    return true;
}

bool is_overlay_code(const void* address) {
    auto value = reinterpret_cast<std::uintptr_t>(address);
    ModuleRange range = overlay_range();
    return value >= range.begin && value < range.end;
}

HMODULE overlay_module() {
    static const HMODULE module = [] {
        HMODULE handle = nullptr;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&overlay_module), &handle);
        return handle;
    }();
    return module;
}

}  // namespace reflektortts
