// Code hooks through MinHook, checked every half second and put back in front when another overlay
// cuts them out of the chain (as RivaTuner Statistics Server does), and the overlay DLL's address
// range, to tell its own calls apart.

#include "hooks/code_hook.h"

#include <MinHook.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include "diagnostics/describe_address.h"
#include "log.h"
#include "memory/addresses.h"
#include "memory/functions.h"
#include "memory/pe_image.h"

namespace reflektortts {
namespace {

std::mutex g_mutex;
bool g_initialized = false;
std::unordered_map<void*, void*> g_trampolines;  // Hooked function -> its trampoline.

// The first bytes of a function, enough to hold any jump a hook writes there (FF 25 disp32 is 6).
using CodeBytes = std::array<std::uint8_t, 8>;

// Each hook is checked this often (see restore_cut_hooks).
constexpr DWORD kWatchMs = 500;

struct WatchedHook {
    void* target;
    void* detour;
    void** original;
    CodeBytes replaced;  // What our hook overwrote.
    CodeBytes written;   // What it wrote.
    bool watched = true;
};
std::vector<WatchedHook> g_watched;
bool g_watching = false;

CodeBytes read_code(const void* address) {
    CodeBytes bytes{};
    ReadProcessMemory(GetCurrentProcess(), address, bytes.data(), bytes.size(), nullptr);
    return bytes;
}

// The jumps hooking libraries write: E9 rel32, FF 25 (indirect, through [rip+disp32] on 64-bit and
// [disp32] on 32-bit), and the short EB rel8 of hot-patching.
bool is_jump(const CodeBytes& code) {
    std::uint8_t first = std::get<0>(code);
    std::uint8_t second = std::get<1>(code);
    return first == 0xE9 || first == 0xEB || (first == 0xFF && second == 0x25);
}

// The 32-bit value at offset in code: a jump's displacement or address.
std::int32_t value_at(const CodeBytes& code, std::size_t offset) {
    std::int32_t value = 0;
    std::memcpy(&value, std::span(code).subspan(offset, sizeof(value)).data(), sizeof(value));
    return value;
}

// Where the jump in code, found at address, leads; nullptr for a short jump, which only reaches a
// longer one next to it.
void* jump_destination(const CodeBytes& code, const void* address) {
    std::uint8_t first = std::get<0>(code);
    std::uint8_t second = std::get<1>(code);
    if (first == 0xE9) {
        return pointer_at<void>(displaced(address_of(address) + 5, value_at(code, 1)));
    }
    if (first == 0xFF && second == 0x25) {
#ifdef _WIN64
        const void* slot = pointer_at<const void>(displaced(address_of(address) + 6, value_at(code, 2)));
#else
        const void* slot = pointer_at<const void>(static_cast<std::uint32_t>(value_at(code, 2)));
#endif
        void* destination = nullptr;
        ReadProcessMemory(GetCurrentProcess(), slot, static_cast<void*>(&destination), sizeof(destination), nullptr);
        return destination;
    }
    return nullptr;
}

// Hooks target with MinHook and watches the hook. The caller holds g_mutex.
bool install(void* target, void* detour, void** original) {
    CodeBytes replaced = read_code(target);
    MH_STATUS status = MH_CreateHook(target, detour, original);
    if (status == MH_OK) {
        status = MH_EnableHook(target);
    }
    if (status != MH_OK) {
        log_message(std::string("Cannot hook a function: ") + MH_StatusToString(status));
        return false;
    }
    g_trampolines[target] = *original;
    g_watched.push_back(
        {.target = target, .detour = detour, .original = original, .replaced = replaced, .written = read_code(target)});
    return true;
}

// Our hook is cut out of the chain when the start of the function no longer holds our jump but
// either the jump we overwrote (an overlay put its own back) or no jump at all (an overlay
// restored the original code: RivaTuner Statistics Server does so on every call, removing its
// hook while it calls the function and putting it back after). Hooking the code the overwritten
// jump leads to, the overlay's own hook, puts ours back in front: us, then the overlay, then the
// function. A jump of another kind belongs to an overlay that hooked after us, whose chain still
// runs through ours, so that is left alone.
void restore_cut_hooks() {
    std::scoped_lock lock(g_mutex);
    // By index and by copy: install adds entries as it goes, which can move the vector's elements, so
    // a range-based loop, as clang-tidy's modernize-loop-convert would have it, would read freed memory.
    for (std::size_t i = 0; i < g_watched.size(); ++i) {  // NOLINT(modernize-loop-convert)
        WatchedHook& watched = g_watched.at(i);  // Used only until install below adds an entry.
        if (!watched.watched) {
            continue;
        }
        CodeBytes current = read_code(watched.target);
        if (current == watched.written || (is_jump(current) && current != watched.replaced)) {
            continue;
        }
        WatchedHook cut = watched;
        watched.watched = false;  // Settled either way; a new hook gets an entry of its own.
        void* destination = is_jump(cut.replaced) ? jump_destination(cut.replaced, cut.target) : nullptr;
        void* trampoline = nullptr;
        if (destination == nullptr || g_trampolines.contains(destination) ||
            !install(destination, cut.detour, &trampoline)) {
            log_message("Another overlay removed our hook on " + describe_address(cut.target) +
                        ", which could not be put back");
            continue;
        }
        *cut.original = trampoline;
        // hook_function hands this trampoline out for the target from now on: the first one leads
        // to the other overlay's code, which now jumps back to us.
        g_trampolines[cut.target] = trampoline;
        log_message("Another overlay removed our hook on " + describe_address(cut.target) + "; hooked its code at " +
                    describe_address(destination) + " instead");
    }
}

DWORD WINAPI watch_hooks(LPVOID) {
    for (;;) {
        Sleep(kWatchMs);
        restore_cut_hooks();
    }
}

struct ModuleRange {
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
};

ModuleRange overlay_range() {
    static const ModuleRange range = [] {
        std::uintptr_t base = address_of(overlay_module());
        const IMAGE_NT_HEADERS& headers = pe_headers(pointer_at<const BYTE>(base));
        return ModuleRange{.begin = base, .end = base + headers.OptionalHeader.SizeOfImage};
    }();
    return range;
}

}  // namespace

bool hook_function(void* target, void* detour, void** original) {
    std::scoped_lock lock(g_mutex);
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
    if (!install(target, detour, original)) {
        return false;
    }
    if (!g_watching) {
        g_watching = true;
        if (HANDLE thread = CreateThread(nullptr, 0, watch_hooks, nullptr, 0, nullptr)) {
            CloseHandle(thread);
        }
    }
    return true;
}

bool is_overlay_code(const void* address) {
    std::uintptr_t value = address_of(address);
    ModuleRange range = overlay_range();
    return value >= range.begin && value < range.end;
}

HMODULE overlay_module() {
    static const HMODULE module = [] {
        HMODULE handle = nullptr;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCWSTR>(code_address(&overlay_module)), &handle);
        return handle;
    }();
    return module;
}

}  // namespace reflektortts
