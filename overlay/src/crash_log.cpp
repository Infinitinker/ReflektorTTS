#include "crash_log.h"

#include <windows.h>

#include <atomic>
#include <cstdio>

#include "log.h"

namespace reflektortts {
namespace {

constexpr int kMaxLoggedCrashes = 5;
std::atomic<int> g_logged = 0;

bool is_crash(DWORD code) {
    switch (code) {
        case EXCEPTION_ACCESS_VIOLATION:
        case EXCEPTION_ILLEGAL_INSTRUCTION:
        case EXCEPTION_PRIV_INSTRUCTION:
        case EXCEPTION_STACK_OVERFLOW:
        case EXCEPTION_INT_DIVIDE_BY_ZERO:
            return true;
        default:
            return false;
    }
}

LONG CALLBACK log_crash(EXCEPTION_POINTERS* exception) {
    const EXCEPTION_RECORD* record = exception->ExceptionRecord;
    if (!is_crash(record->ExceptionCode) || g_logged++ >= kMaxLoggedCrashes) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    void* address = record->ExceptionAddress;
    HMODULE module = nullptr;
    char name[MAX_PATH] = "?";
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCSTR>(address), &module)) {
        GetModuleFileNameA(module, name, MAX_PATH);
    }
    char text[MAX_PATH + 160];
    // For access violations, the second parameter is the address that could not be read or written.
    std::snprintf(text, sizeof(text), "Exception 0x%08lX at %p (%s+0x%lX), data address %p", record->ExceptionCode,
                  address, name,
                  static_cast<unsigned long>(reinterpret_cast<char*>(address) - reinterpret_cast<char*>(module)),
                  record->NumberParameters > 1 ? reinterpret_cast<void*>(record->ExceptionInformation[1]) : nullptr);
    log_message(text);
    return EXCEPTION_CONTINUE_SEARCH;
}

}  // namespace

void install_crash_log() {
    AddVectoredExceptionHandler(0, log_crash);
}

}  // namespace reflektortts
