// Opens the SDL window and ImGui, and runs the frame loop: it draws only while something happens,
// follows the display's scale, and keeps drawing while the user drags the window's edge.

#include "panel_window.h"

#include <SDL3/SDL.h>
#include <imgui.h>
#include <imgui_impl_sdl3.h>
#include <imgui_impl_sdlrenderer3.h>

#include <cmath>
#include <optional>
#include <stdexcept>
#include <string>

#include "api_client.h"
#include "log.h"
#include "panel_ui.h"
#include "placement.h"
#include "startup_error.h"
#include "system_font.h"
#include "ui_scale.h"
#include "wakeup.h"

namespace reflektortts {
namespace {

// At 100% display scale.
constexpr float kFontSize = 16.0f;
// How long frames keep coming after the user's last input: ImGui's hover delays and animations need
// frames without an event. Then the window waits for the next one.
constexpr Uint64 kActiveMs = 1000;
// The frames drawn when the API client's state changes: ImGui's boxes take a frame to fit their
// new contents.
constexpr int kFramesPerChange = 2;
// The time between those frames when the renderer cannot wait for the display's refresh.
constexpr Sint32 kFrameMs = 16;

class WindowError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

std::string sdl_error(const std::string& what) {
    return what + " (" + SDL_GetError() + ")";
}

// What the window is made of, released in reverse order, also when it was opened only in part.
struct Window {
    bool sdl = false;
    SDL_Window* window = nullptr;
    SDL_Renderer* renderer = nullptr;
    bool imgui = false;
    bool platform_backend = false;
    bool renderer_backend = false;
    bool vsync = false;

    Window() = default;
    Window(const Window&) = delete;
    Window& operator=(const Window&) = delete;
    ~Window() {
        if (renderer_backend) {
            ImGui_ImplSDLRenderer3_Shutdown();
        }
        if (platform_backend) {
            ImGui_ImplSDL3_Shutdown();
        }
        if (imgui) {
            ImGui::DestroyContext();
        }
        if (renderer != nullptr) {
            SDL_DestroyRenderer(renderer);
        }
        if (window != nullptr) {
            SDL_DestroyWindow(window);
        }
        if (sdl) {
            disable_wakeups();
            SDL_Quit();
        }
    }
};

// Throws WindowError with a message for the user if a part cannot be made.
void open_window(Window& parts) {
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        throw WindowError(sdl_error("The settings window cannot open"));
    }
    parts.sdl = true;
    enable_wakeups();

    // Hidden until run() has sized and placed it.
    parts.window = SDL_CreateWindow("Settings - ReflektorTTS", 1, 1,
                                    SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIDDEN | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (parts.window == nullptr) {
        throw WindowError(sdl_error("The settings window cannot open"));
    }
    // SDL picks the renderer: Direct3D 11 where it works, else Direct3D 12, 9, OpenGL or software.
    parts.renderer = SDL_CreateRenderer(parts.window, nullptr);
    if (parts.renderer == nullptr) {
        throw WindowError(sdl_error("The settings window cannot draw"));
    }
    log_message(std::string("Drawing with SDL's ") + SDL_GetRendererName(parts.renderer) + " renderer");
    parts.vsync = SDL_SetRenderVSync(parts.renderer, 1);
    if (!parts.vsync) {
        log_message(sdl_error("Cannot wait for the display's refresh; frames are timed instead"));
    }

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    parts.imgui = true;
    ImGui::GetIO().IniFilename = nullptr;
    load_system_font(kFontSize);
    if (!ImGui_ImplSDL3_InitForSDLRenderer(parts.window, parts.renderer)) {
        throw WindowError("The settings window cannot read input.");
    }
    parts.platform_backend = true;
    if (!ImGui_ImplSDLRenderer3_Init(parts.renderer)) {
        throw WindowError("The settings window cannot draw.");
    }
    parts.renderer_backend = true;
}

// Handles one event; returns false once the user closes the window.
bool handle_event(const SDL_Event& event, SDL_Window* window) {
    ImGui_ImplSDL3_ProcessEvent(&event);
    switch (event.type) {
        case SDL_EVENT_QUIT:
            return false;
        case SDL_EVENT_WINDOW_CLOSE_REQUESTED:
            return event.window.windowID != SDL_GetWindowID(window);
        case kWakeupEvent:
            wakeup_received();
            break;
        case SDL_EVENT_RENDER_DEVICE_RESET:
            // The textures were lost with the device; ImGui uploads them again on the next frame.
            ImGui_ImplSDLRenderer3_DestroyDeviceObjects();
            break;
        case SDL_EVENT_RENDER_DEVICE_LOST:
            log_message("The graphics device was lost; the window may stay blank until it is opened again");
            break;
        default:
            break;
    }
    return true;
}

// Follows the display's scale, which changes when the window moves to another display or the user
// changes it, and keeps the window from getting smaller than it opened.
class ScaleFollower {
public:
    ScaleFollower(SDL_Window* window, WindowSize smallest)
        : window_(window), smallest_(smallest), base_(ImGui::GetStyle()) {}

    void update() {
        float scale = window_ui_scale(window_);
        if (scale == scale_) {
            return;
        }
        scale_ = scale;
        apply_ui_scale(base_, scale);
        SDL_SetWindowMinimumSize(window_, static_cast<int>(std::lround(smallest_.width * scale)),
                                 static_cast<int>(std::lround(smallest_.height * scale)));
    }

private:
    SDL_Window* window_;
    WindowSize smallest_;  // At 100% display scale.
    ImGuiStyle base_;
    float scale_ = 0.0f;
};

void draw_frame(const Window& parts, const CoreState& state) {
    ImGui_ImplSDLRenderer3_NewFrame();
    ImGui_ImplSDL3_NewFrame();
    ImGui::NewFrame();
    draw_panel_ui(state);
    ImGui::Render();

    const ImGuiIO& io = ImGui::GetIO();
    // The panel's background, under ImGui's slightly transparent window.
    const ImVec4& background = ImGui::GetStyle().Colors[ImGuiCol_WindowBg];
    SDL_SetRenderScale(parts.renderer, io.DisplayFramebufferScale.x, io.DisplayFramebufferScale.y);
    SDL_SetRenderDrawColorFloat(parts.renderer, background.x, background.y, background.z, 1.0f);
    SDL_RenderClear(parts.renderer);
    ImGui_ImplSDLRenderer3_RenderDrawData(ImGui::GetDrawData(), parts.renderer);
    SDL_RenderPresent(parts.renderer);
}

// Draws the window's frames: from the frame loop, and while the user drags the window's edge.
// Windows then runs a loop of its own until the mouse button is released, so SDL_WaitEventTimeout
// does not return; from a timer in that loop, on the main thread, SDL sends
// SDL_EVENT_WINDOW_EXPOSED with data1 = 1, to be drawn for right in an event watch.
class Frames {
public:
    Frames(const Window& parts, WindowSize smallest) : parts_(parts), scale_(parts.window, smallest) {
        if (!SDL_AddEventWatch(&Frames::on_event, this)) {
            log_message(sdl_error("The window will not be redrawn while it is resized"));
        }
    }
    Frames(const Frames&) = delete;
    Frames& operator=(const Frames&) = delete;
    ~Frames() {
        SDL_RemoveEventWatch(&Frames::on_event, this);
    }

    // Follows the display's scale and the window's title, then draws a frame; does nothing while
    // the window is minimized or a frame is being drawn already.
    void draw() {
        if (drawing_ || (SDL_GetWindowFlags(parts_.window) & SDL_WINDOW_MINIMIZED) != 0) {
            return;
        }
        drawing_ = true;
        scale_.update();
        CoreState state = core_state();
        if (std::string wanted = window_title(state); wanted != title_) {
            title_ = wanted;
            SDL_SetWindowTitle(parts_.window, title_.c_str());
        }
        draw_frame(parts_, state);
        drawing_ = false;
    }

private:
    // Runs on the thread that sent the event (the API client's threads send wakeups), so it draws
    // only for the live-resize expose events, which come on the main thread.
    static bool SDLCALL on_event(void* userdata, SDL_Event* event) {
        auto* frames = static_cast<Frames*>(userdata);
        if (event->type == SDL_EVENT_WINDOW_EXPOSED && event->window.data1 == 1 && SDL_IsMainThread() &&
            event->window.windowID == SDL_GetWindowID(frames->parts_.window)) {
            frames->draw();
        }
        return true;
    }

    const Window& parts_;
    ScaleFollower scale_;
    std::string title_;
    bool drawing_ = false;
};

void run(const Window& parts, const std::optional<Dock>& dock) {
    // ImGui's style is not scaled yet, so its scrollbar is as wide as at 100%.
    WindowSize size = place_window(parts.window, dock, ImGui::GetStyle().ScrollbarSize);
    Frames frames(parts, size);
    frames.draw();
    SDL_ShowWindow(parts.window);
    Uint64 last_input_ms = SDL_GetTicks();
    int frames_owed = 0;
    for (;;) {
        bool minimized = (SDL_GetWindowFlags(parts.window) & SDL_WINDOW_MINIMIZED) != 0;
        bool active = !minimized && (frames_owed > 0 || SDL_GetTicks() - last_input_ms < kActiveMs);
        Sint32 timeout = !active ? -1 : parts.vsync ? 0 : kFrameMs;
        SDL_Event event;
        for (bool received = SDL_WaitEventTimeout(&event, timeout); received; received = SDL_PollEvent(&event)) {
            if (event.type == kWakeupEvent) {
                frames_owed = kFramesPerChange;
            } else {
                last_input_ms = SDL_GetTicks();
            }
            if (!handle_event(event, parts.window)) {
                return;
            }
        }
        frames.draw();
        if (frames_owed > 0) {
            --frames_owed;
        }
    }
}

}  // namespace

int run_panel_window(const std::optional<Dock>& dock) {
    try {
        Window parts;
        open_window(parts);
        run(parts, dock);
        return 0;
    } catch (const WindowError& error) {
        report_startup_error(error.what());
        return 1;
    }
}

}  // namespace reflektortts
