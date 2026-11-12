// A hidden window for creating throwaway devices that reveal where API methods live: a device
// needs a window, and the app's own is left alone.

#pragma once

#include <windows.h>

namespace reflektortts {

class ProbeWindow {
public:
    ProbeWindow();
    ~ProbeWindow();
    ProbeWindow(const ProbeWindow&) = delete;
    ProbeWindow& operator=(const ProbeWindow&) = delete;

    HWND handle() const { return window_; }

private:
    HWND window_;
};

}  // namespace reflektortts
