#include "probe_window.h"

namespace reflektortts {
namespace {

constexpr wchar_t kClassName[] = L"ReflektorTTSProbe";

}  // namespace

ProbeWindow::ProbeWindow() {
    WNDCLASSEXW window_class{};
    window_class.cbSize = sizeof(window_class);
    window_class.lpfnWndProc = DefWindowProcW;
    window_class.hInstance = GetModuleHandleW(nullptr);
    window_class.lpszClassName = kClassName;
    RegisterClassExW(&window_class);
    window_ = CreateWindowExW(0, kClassName, L"", WS_OVERLAPPEDWINDOW, 0, 0, 100, 100, nullptr, nullptr,
                              window_class.hInstance, nullptr);
}

ProbeWindow::~ProbeWindow() {
    DestroyWindow(window_);
    UnregisterClassW(kClassName, GetModuleHandleW(nullptr));
}

}  // namespace reflektortts
