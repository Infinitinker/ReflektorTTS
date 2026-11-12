// Measures the window's visible frame around its client area: through DWM on Windows, without the
// invisible resize borders, and from SDL's borders elsewhere.

#include "window_frame.h"

#include <string>

#include "log.h"

#ifdef _WIN32
#include <windows.h>
#include <dwmapi.h>
#endif

namespace reflektortts {

#ifdef _WIN32

FrameInsets visible_frame_insets(SDL_Window* window) {
    auto* hwnd = static_cast<HWND>(
        SDL_GetPointerProperty(SDL_GetWindowProperties(window), SDL_PROP_WINDOW_WIN32_HWND_POINTER, nullptr));
    RECT client{};
    POINT origin{};
    RECT frame{};
    // SDL makes the process per-monitor DPI aware, so all three are in physical pixels; the frame
    // bounds are anyway. They are known for a window not shown yet too.
    if (hwnd == nullptr || !GetClientRect(hwnd, &client) || !ClientToScreen(hwnd, &origin) ||
        FAILED(DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &frame, sizeof(frame)))) {
        log_message("Cannot measure the window's frame; it may open a few pixels off its place");
        return {};
    }
    return {origin.x - frame.left, origin.y - frame.top, frame.right - (origin.x + client.right),
            frame.bottom - (origin.y + client.bottom)};
}

#else

FrameInsets visible_frame_insets(SDL_Window* window) {
    FrameInsets insets;
    if (!SDL_GetWindowBordersSize(window, &insets.top, &insets.left, &insets.bottom, &insets.right)) {
        log_message(std::string("Cannot measure the window's frame: ") + SDL_GetError());
        return {};
    }
    // SDL's borders are in window coordinates.
    float density = SDL_GetWindowPixelDensity(window);
    auto pixels = [density](int size) { return static_cast<int>(static_cast<float>(size) * density + 0.5f); };
    return {pixels(insets.left), pixels(insets.top), pixels(insets.right), pixels(insets.bottom)};
}

#endif

}  // namespace reflektortts
