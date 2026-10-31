#include "dll_load_watch.h"

namespace reflektortts {
namespace {

// From the Windows SDK documentation of LdrRegisterDllNotification; not in MinGW's headers.
constexpr ULONG kDllLoaded = 1;
using NotificationFn = VOID(CALLBACK*)(ULONG reason, const void* data, PVOID context);
using RegisterFn = LONG(NTAPI*)(ULONG flags, NotificationFn notification, PVOID context, PVOID* cookie);

// The loader lock is held here, so the event only wakes a thread that does the work.
VOID CALLBACK on_notification(ULONG reason, const void*, PVOID context) {
    if (reason == kDllLoaded) {
        SetEvent(static_cast<HANDLE>(context));
    }
}

}  // namespace

bool signal_on_dll_load(HANDLE event) {
    auto register_notification = reinterpret_cast<RegisterFn>(
        GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "LdrRegisterDllNotification"));
    PVOID cookie = nullptr;
    return register_notification != nullptr && register_notification(0, &on_notification, event, &cookie) >= 0;
}

}  // namespace reflektortts
