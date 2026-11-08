#include "diagnostics/crash_log.h"

#include <windows.h>

#include <atomic>
#include <cstdio>
#include <string>

#include "diagnostics/describe_address.h"
#include "log.h"

namespace reflektortts {
namespace {

constexpr int kMaxLoggedCrashes = 5;
std::atomic<int> g_logged = 0;

// A stack overflow is left out: the handler would run on the few KB of stack left, and
// overflowing it again would end the process before the app's own handler sees it.
bool is_crash(DWORD code) {
    switch (code) {
        case EXCEPTION_ACCESS_VIOLATION:
        case EXCEPTION_ILLEGAL_INSTRUCTION:
        case EXCEPTION_PRIV_INSTRUCTION:
        case EXCEPTION_INT_DIVIDE_BY_ZERO:
            return true;
        default:
            return false;
    }
}

#ifdef _WIN64
constexpr int kMaxLoggedFrames = 12;

// Walks the stack from the crash, as a debugger would, using the unwind data of 64-bit code.
void log_call_stack(CONTEXT context) {
    for (int frame = 0; frame < kMaxLoggedFrames && context.Rip != 0; ++frame) {
        log_message("  called from " + describe_address(reinterpret_cast<const void*>(context.Rip)));
        DWORD64 image_base = 0;
        RUNTIME_FUNCTION* function = RtlLookupFunctionEntry(context.Rip, &image_base, nullptr);
        if (function == nullptr) {
            // A leaf function: the return address is on top of the stack.
            context.Rip = *reinterpret_cast<DWORD64*>(context.Rsp);
            context.Rsp += sizeof(DWORD64);
        } else {
            void* handler_data = nullptr;
            DWORD64 establisher_frame = 0;
            RtlVirtualUnwind(UNW_FLAG_NHANDLER, image_base, context.Rip, function, &context, &handler_data,
                             &establisher_frame, nullptr);
        }
    }
}
#endif

LONG CALLBACK log_crash(EXCEPTION_POINTERS* exception) {
    const EXCEPTION_RECORD* record = exception->ExceptionRecord;
    if (!is_crash(record->ExceptionCode) || g_logged++ >= kMaxLoggedCrashes) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    char text[64];
    // For access violations, the second parameter is the address that could not be read or written.
    std::snprintf(text, sizeof(text), ", data address %p",
                  record->NumberParameters > 1 ? reinterpret_cast<void*>(record->ExceptionInformation[1]) : nullptr);
    char code[32];
    std::snprintf(code, sizeof(code), "Exception 0x%08lX at ", record->ExceptionCode);
    log_message(code + describe_address(record->ExceptionAddress) + text);
#ifdef _WIN64
    log_call_stack(*exception->ContextRecord);
#endif
    return EXCEPTION_CONTINUE_SEARCH;
}

}  // namespace

// First in line, so the crash is logged even when the app's own crash handler ends the process.
void install_crash_log() {
    AddVectoredExceptionHandler(1, log_crash);
}

}  // namespace reflektortts
